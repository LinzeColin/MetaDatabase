"""比赛结果模型：带时间衰减与岭惩罚的泊松进球模型（Dixon-Coles 低比分修正）。

    log(主队期望进球) = 赛事截距 + 主场优势 + 主队进攻 - 客队防守
    log(客队期望进球) = 赛事截距 + 客队进攻 - 主队防守

进攻/防守 = 「所属联赛整体水平」+「球队自己相对联赛的偏离」，后者用岭惩罚拉向 0：
样本少的球队会自动靠近所在联赛的平均，而不是被几场比赛带偏。欧冠比赛把各联赛连在同一个模型里，
所以跨联赛的强弱由数据自己估出来，不靠人工排名。

不确定度：把岭惩罚当高斯先验，取拉普拉斯近似的后验协方差，抽样得到每场比赛概率的 10%-90% 区间。
这是「参数不确定」，不包括伤病、阵容、天气等模型看不到的信息。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy import sparse
from scipy.special import gammaln

from . import config

OTHER_GROUP = "OTHER"


def _days(a: str, b: str) -> int:
    ya, ma, da = (int(x) for x in a.split("-"))
    yb, mb, db = (int(x) for x in b.split("-"))
    return (date(ya, ma, da) - date(yb, mb, db)).days


@dataclass
class TrainMatch:
    date: str
    comp: str
    home: str  # 球队键
    away: str
    hg: int
    ag: int


@dataclass
class Fitted:
    as_of: str
    comps: list[str]
    groups: list[str]
    teams: list[str]
    team_group: dict[str, str]
    theta: np.ndarray
    cov_chol: np.ndarray            # 后验协方差的 Cholesky 因子（下三角）
    rho: float
    n_matches: int
    n_eff: dict[str, float]         # 球队 -> 加权有效场数
    last_played: dict[str, str]     # 球队 -> 最近一场（训练集内）
    # 参数在 theta 里的位置
    _ix: dict = field(default_factory=dict)

    # ---- 参数取用
    def _mu(self, comp: str) -> float:
        i = self.comps.index(comp) if comp in self.comps else None
        return float(self.theta[i]) if i is not None else float(np.mean(self.theta[: len(self.comps)]))

    def _idx(self, team: str) -> int | None:
        return self._ix["team"].get(team)

    def _group_idx(self, team: str) -> int:
        g = self.team_group.get(team, OTHER_GROUP)
        return self._ix["group"].get(g, self._ix["group"].get(OTHER_GROUP, 0))

    def linear_terms(self, theta: np.ndarray, home: str, away: str, comp: str) -> tuple[np.ndarray, np.ndarray]:
        """对一组参数向量（形状 (S,p) 或 (p,)）返回 (log λ主, log λ客)。"""
        ix = self._ix
        ncomp = len(self.comps)
        ci = self.comps.index(comp) if comp in self.comps else None
        mu = theta[..., ci] if ci is not None else theta[..., :ncomp].mean(axis=-1)
        eta = theta[..., ix["eta"]]
        gh, ga = self._group_idx(home), self._group_idx(away)
        ah = theta[..., ix["A"] + gh]
        aa = theta[..., ix["A"] + ga]
        dh = theta[..., ix["D"] + gh]
        da = theta[..., ix["D"] + ga]
        th, ta = self._idx(home), self._idx(away)
        a_h = theta[..., ix["a"] + th] if th is not None else 0.0
        d_h = theta[..., ix["d"] + th] if th is not None else 0.0
        a_a = theta[..., ix["a"] + ta] if ta is not None else 0.0
        d_a = theta[..., ix["d"] + ta] if ta is not None else 0.0
        lh = mu + eta + ah + a_h - da - d_a
        la = mu + aa + a_a - dh - d_h
        return lh, la

    # ---- 预测
    def predict(self, home: str, away: str, comp: str, *, draws: int = 0, seed: int = 7) -> dict:
        lh, la = self.linear_terms(self.theta, home, away, comp)
        lam_h, lam_a = float(np.exp(lh)), float(np.exp(la))
        mat = score_matrix(lam_h, lam_a, self.rho)
        out = summarize_matrix(mat)
        out.update({"lam_home": lam_h, "lam_away": lam_a})
        if draws:
            rng = np.random.default_rng(seed)
            z = rng.standard_normal((draws, self.theta.size))
            samples = self.theta + z @ self.cov_chol.T
            slh, sla = self.linear_terms(samples, home, away, comp)
            mats = score_matrix_batch(np.exp(slh), np.exp(sla), self.rho)
            ph = np.tril(np.ones_like(mats[0]), -1)  # i>j：行是主队进球
            p_home = (mats * ph).sum(axis=(1, 2))
            p_draw = np.einsum("sii->s", mats)
            p_away = 1.0 - p_home - p_draw
            lo = lambda x: float(np.percentile(x, 10))  # noqa: E731
            hi = lambda x: float(np.percentile(x, 90))  # noqa: E731
            out["interval"] = {"home": [lo(p_home), hi(p_home)], "draw": [lo(p_draw), hi(p_draw)],
                               "away": [lo(p_away), hi(p_away)]}
        return out

    def team_strength(self, team: str) -> dict | None:
        """把球队的进攻/防守折算成「对平均球队、中立场、每场预期净胜球」。"""
        ti = self._idx(team)
        if ti is None:
            return None
        ix = self._ix
        g = self._group_idx(team)
        att = self.theta[ix["A"] + g] + self.theta[ix["a"] + ti]
        dfn = self.theta[ix["D"] + g] + self.theta[ix["d"] + ti]
        return {"att": float(att), "def": float(dfn)}


# ------------------------------------------------------------------ 比分矩阵
def _pois_logpmf(k: np.ndarray, lam: np.ndarray) -> np.ndarray:
    return k * np.log(lam) - lam - gammaln(k + 1)


def score_matrix(lam_h: float, lam_a: float, rho: float, n: int = config.MAX_GOALS) -> np.ndarray:
    return score_matrix_batch(np.array([lam_h]), np.array([lam_a]), rho, n)[0]


def score_matrix_batch(lam_h: np.ndarray, lam_a: np.ndarray, rho: float, n: int = config.MAX_GOALS) -> np.ndarray:
    k = np.arange(n + 1, dtype=float)
    ph = np.exp(_pois_logpmf(k[None, :], lam_h[:, None]))   # (S, n+1)
    pa = np.exp(_pois_logpmf(k[None, :], lam_a[:, None]))
    mat = ph[:, :, None] * pa[:, None, :]
    mat[:, 0, 0] *= 1 - lam_h * lam_a * rho
    mat[:, 0, 1] *= 1 + lam_h * rho
    mat[:, 1, 0] *= 1 + lam_a * rho
    mat[:, 1, 1] *= 1 - rho
    mat = np.clip(mat, 0, None)
    return mat / mat.sum(axis=(1, 2), keepdims=True)


def summarize_matrix(mat: np.ndarray) -> dict:
    n = mat.shape[0]
    i, j = np.indices((n, n))
    p_home = float(mat[i > j].sum())
    p_draw = float(mat[i == j].sum())
    p_away = float(mat[i < j].sum())
    top = np.dstack(np.unravel_index(np.argsort(-mat, axis=None)[:3], mat.shape))[0]
    return {
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "p_over25": float(mat[(i + j) >= 3].sum()),
        "p_btts": float(mat[(i >= 1) & (j >= 1)].sum()),
        "top_scores": [{"score": f"{int(a)}-{int(b)}", "p": float(mat[a, b])} for a, b in top],
        "exp_goals_home": float((mat.sum(axis=1) * np.arange(n)).sum()),
        "exp_goals_away": float((mat.sum(axis=0) * np.arange(n)).sum()),
    }


# ------------------------------------------------------------------ 拟合
def fit(matches: list[TrainMatch], team_group: dict[str, str], as_of: str) -> Fitted:
    """只用 date < as_of 的比赛。team_group：球队 -> 所属联赛（无国内联赛记录的球队用 OTHER）。"""
    ms = [m for m in matches if m.date < as_of]
    if len(ms) < 50:
        raise ValueError(f"训练样本太少：{len(ms)}")
    comps = sorted({m.comp for m in ms})
    teams = sorted({t for m in ms for t in (m.home, m.away)})
    groups = sorted({team_group.get(t, OTHER_GROUP) for t in teams} | {OTHER_GROUP})
    nc, ng, nt = len(comps), len(groups), len(teams)
    ix = {"eta": nc, "A": nc + 1, "D": nc + 1 + ng, "a": nc + 1 + 2 * ng, "d": nc + 1 + 2 * ng + nt,
          "team": {t: i for i, t in enumerate(teams)}, "group": {g: i for i, g in enumerate(groups)}}
    p = nc + 1 + 2 * ng + 2 * nt
    tg = {t: team_group.get(t, OTHER_GROUP) for t in teams}

    n = len(ms)
    ci = np.array([comps.index(m.comp) for m in ms])
    hi = np.array([ix["team"][m.home] for m in ms])
    ai = np.array([ix["team"][m.away] for m in ms])
    gh = np.array([ix["group"][tg[m.home]] for m in ms])
    ga = np.array([ix["group"][tg[m.away]] for m in ms])
    y = np.concatenate([[m.hg for m in ms], [m.ag for m in ms]]).astype(float)
    age = np.array([_days(as_of, m.date) for m in ms], dtype=float)
    w1 = 0.5 ** (age / config.HALF_LIFE_DAYS)
    w = np.concatenate([w1, w1])

    rows, cols, vals = [], [], []

    def put(r, c, v):
        rows.append(r); cols.append(c); vals.append(np.full(r.shape, v, dtype=float))

    r_h, r_a = np.arange(n), np.arange(n) + n
    put(r_h, ci, 1.0); put(r_h, np.full(n, ix["eta"]), 1.0)
    put(r_h, ix["A"] + gh, 1.0); put(r_h, ix["a"] + hi, 1.0)
    put(r_h, ix["D"] + ga, -1.0); put(r_h, ix["d"] + ai, -1.0)
    put(r_a, ci, 1.0)
    put(r_a, ix["A"] + ga, 1.0); put(r_a, ix["a"] + ai, 1.0)
    put(r_a, ix["D"] + gh, -1.0); put(r_a, ix["d"] + hi, -1.0)
    X = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * n, p))

    prec = np.zeros(p)
    prec[ix["A"]: ix["A"] + 2 * ng] = 1.0 / config.RIDGE_GROUP_SD ** 2
    prec[ix["a"]: p] = 1.0 / config.RIDGE_TEAM_SD ** 2
    P = np.diag(prec)

    def objective(th):
        eta = np.clip(X @ th, -10, 3)
        lam = np.exp(eta)
        return float(np.sum(w * (lam - y * eta)) + 0.5 * th @ (prec * th)), lam

    theta = np.zeros(p)
    theta[:nc] = math.log(max(float(np.mean(y)), 0.5))
    f, lam = objective(theta)
    for _ in range(60):
        grad = X.T @ (w * (lam - y)) + prec * theta
        H = (X.T @ sparse.diags(w * lam) @ X).toarray() + P
        step = np.linalg.solve(H, grad)
        t = 1.0
        while t > 1e-4:
            f2, lam2 = objective(theta - t * step)
            if f2 <= f + 1e-12:
                break
            t *= 0.5
        theta = theta - t * step
        done = abs(f - f2) < 1e-9 * max(1.0, abs(f))
        f, lam = f2, lam2
        if done:
            break
    H = (X.T @ sparse.diags(w * lam) @ X).toarray() + P
    cov = np.linalg.inv(H)
    cov = (cov + cov.T) / 2
    chol = np.linalg.cholesky(cov + 1e-10 * np.eye(p))

    lam_h, lam_a = lam[:n], lam[n:]
    rho = _fit_rho(np.array([m.hg for m in ms]), np.array([m.ag for m in ms]), lam_h, lam_a, w1)

    n_eff: dict[str, float] = {}
    last: dict[str, str] = {}
    for m, wi in zip(ms, w1):
        for t in (m.home, m.away):
            n_eff[t] = n_eff.get(t, 0.0) + float(wi)
            if t not in last or m.date > last[t]:
                last[t] = m.date
    return Fitted(as_of=as_of, comps=comps, groups=groups, teams=teams, team_group=tg, theta=theta,
                  cov_chol=chol, rho=rho, n_matches=n, n_eff=n_eff, last_played=last, _ix=ix)


def _fit_rho(hg, ag, lam_h, lam_a, w) -> float:
    """在固定 λ 下，用低比分四格的似然估计 Dixon-Coles 的 ρ。"""
    best, best_ll = 0.0, -1e18
    for rho in np.linspace(-0.25, 0.10, 71):
        tau = np.ones_like(lam_h)
        m00 = (hg == 0) & (ag == 0)
        m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0)
        m11 = (hg == 1) & (ag == 1)
        tau[m00] = 1 - lam_h[m00] * lam_a[m00] * rho
        tau[m01] = 1 + lam_h[m01] * rho
        tau[m10] = 1 + lam_a[m10] * rho
        tau[m11] = 1 - rho
        if np.any(tau <= 0):
            continue
        ll = float(np.sum(w * np.log(tau)))
        if ll > best_ll:
            best, best_ll = float(rho), ll
    return best


def outcome_index(hg: int, ag: int) -> int:
    return 0 if hg > ag else (1 if hg == ag else 2)
