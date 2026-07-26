#!/usr/bin/env python3
"""Durable negative oracles for the Stock Skill CI helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_RUNNER = REPO_ROOT / "Stock_Skill/scripts/run_unittests.py"
SAFETY_VALIDATOR = REPO_ROOT / "Stock_Skill/scripts/validate_public_safety.py"
BSS_TASK_GRAPH = (
    REPO_ROOT
    / "Stock_Skill/bottleneck-serenity-skill/task-pack/03_STAGE_PHASE_TASKS.md"
)
BSS_ACCEPTANCE = (
    REPO_ROOT
    / "Stock_Skill/bottleneck-serenity-skill/task-pack/"
    "04_ACCEPTANCE_VALIDATION_STOP.md"
)
SYNTHETIC_FINE_GRAINED_PAT = "github_" + "pat_" + ("A" * 82)
SYNTHETIC_STATELESS_APP_TOKEN = (
    "ghs_"
    + "12345_"
    + "eyJhbGciOiJSUzI1NiJ9."
    + ("A" * 80)
    + "."
    + ("B" * 79)
    + "-"
)
T024_PUBLIC_SAFETY_REPLAY_B85 = (
    "c-p0#X>Z%O7KZ<d;7|7gWlB=q6x<fbr0Glt?KDU-zyLEvKygXb+LlL>(<uh|@Apufw^*^2eh93^;$!lh_bgQZooM"
    "@28#k|Rbx~zro9ec_*OZIN=_HL^>Xb;7WJckXBnfp?Np57Ke9S2Eih5(M7O7HFSSM5r_jt^FY`sb+uO>#9uAH3y`"
    "R~O2vv8(z7M^=`@$1F;4P4E_(e>rU`G>QQAFglE4W==Ae|2&F3&NPd4d1ePxaDh^&*A7nPnT|T`tJmuS!QqwJ}&f"
    "KJHR}*^~Gs!bd?wIHEOW1R8pig<A`ahP?{tXIUX~~Q-cW%^7#1W@$vE12tc|Y(B$(6SCqPHDNR0|!o%w$KrNif3t"
    "L}U7G=%ad_aYJ$lP~?DOwcSgRa~Q_~QM1?jL8C9h@!-{iEi})2}c@eQug*nAZA6R3G$c@e7dHexz*fUE$`YUEsSJ"
    "*ko%t^Q!n!-(ulo<}(*24DRpds7GTjK;uJb55cDPTHL*!+o`LW9`bJvHOD;_e*u*kaDs(?%C@YlbT$namdpCllEy"
    "+vXOWc#BgPd+ifE6xl(8kL2QLsWAe8$FzvgM}kXc#PXy6r<`=@G_GTfi1J4+~EfTH%JRJ#1OY3nnXC#x&HDH-8D)"
    "E@Rs>IF>6ex^mXaMNt=o>;_%{xQw<rb2YLqb;dO#?ujepg*qh%w1WJu+oVB&P}0!hd(}!<RXVU<4UnscE90{&8=H"
    "5NyvCKdf0-lRANKRHYBWH(Jd!{F<?c<uIVANf7?dT+YO#t?8~|Swo4R5e+&#eEJohk7f#z>x`nIiLuB;KO?Ob(NR"
    ")#F9<>^Udbeve{hLemj#?2ul0`gkL?<oDN#|z0wb;Dc0TClXhSfW2oGM!BV~}hJJZ9HI<Vb=w(XN9-PcYF-n^n;~"
    "uiR<WYfQAV*yv3-jojZ$JuP>5K(xo;Bztj+C5$_BJy2&dQKK!*DX<ifa<HRqoMaRZ#d~pVrtju?S!L!l3aLO;+ew"
    "7p)<*~eUH*NW0v<Ptg6yTpz($L?o<_l18lQ<)Hd5cU13|_?(B~mS^zMxHbsfsfsV?t#2<SM1_<4fPNn4`;6YbshX"
    "*-37j$&bZS$dH_X+{2I<ua$W#6KY*@VrqN{J;caBlX+N;@jMz6W(nwJ{cLQsW>!=Sc7{ici2ZJMw7`yvihEBrM|U"
    "i@57O!an!RZ{2EOk7=xSdV^O17lIL^yHJC0o*1o<ECK(G8<3p489;mIkh$IP9+=gc`#H_$bIp&cdnt7Ef$kOm=sv"
    "$M*qGXG-9xYd{mM`?*ySf~Y)8%--F85;C(X^u2OX41oaq=9;&o+#1vw2x*n1b8-LG4-8o!tQ$nf1m4S#Oit-WIN1"
    "jE1C5c>A+EBqNjFm>*IMG+Ey5N@w~@sJXO*Gcxau#bM<@N3`mWtzF#5G%^K_<@09K;&f`$+07o1k(qEjEW;f{AEA"
    "Q&?jcYk2?oTsX<4>KY#$qMJG~=P5h?`)MW+xGTp;ayg1E5>$CiTLC84GrL&XME_<Nxji;zfcv?w}#>Fdc=>Gb4$v"
    "8S~7?EL)V@>#ZlMg@GxY;Y)W_Qh1!9n5rD0!CThHq+TSzp~zOYB18qI>e}k$%`$8Y~30bns$WM{faSs1Ko<5F21?"
    "yHcv}eJoLHH%;|DjxX`g^=)4k^#+tNro)VNK1eO*~6GA-D(Xn*#aIkLxe!9L!*D<<`>+ep+jkG^qzPX2zE(E8=GM"
    "#27YHXq@C9*Qw9Q|Z6YV-jW*2cI+6O(%NZ=M^5#aN8|!2?R`;dC~?+ZYeVy24nE9Be>B%~WTzjiJub_+=cB$TD9R"
    "Ta#$>?3CaW4*y;^tBXqQUG<}N{1XaA!U-GutM|7GE*n#7kfI*xG}6T%*~2LnSe_6Xvt*n-aeSQW?DQhHq-Zr`abi"
    "=gJ!_p^B@CQhX~d<&#tMrG$4|DK5921ss?k<kyxVYDyK4iVSSgfe9eyetQYn#$PzxgK8Q_x_;M1Y-I0fN!w=+G@y"
    "eq3-!g{>00GnDCW@F<7-98ad#-a`=YrpVeZ?<7y&EVzlKYjdgj?T|6FaAKmJ(?YvQ4H)k|L90o9uhq@evo0Cn`N+"
    "EXQ7UXD$s1}Oct`RXy#`5$#BJR_U_lS^NZhZ(Dm8-3lKVTK-c1Ot-x#Qls=tEVxm2F6d99R#9XRSVwpmeiv+C95d"
    "2iY9!476Or9;KE*Se+Rk_)sDZ}#uY_4{J%e-zs!8cjzp}b@%lCcnwNeGU#pdMkHSnV`-(z|291}y1&4nA9a*y*KY"
    "^JRT}-lgxU)R?#=0dM3UF>X_&6Yx+^Qw3_HMC|#oTmv;$UYL9E!J>g!73Xc*_pz^Y1oJ8Lm?Gg~32C6UNO?h!@zQ"
    "V~k{iK}<r;|fiz0u3g1op`-+gav>uSvhnGw=S&QP3s9Fl2_Qo%J!Frhp)I_6LL<S^AhIxquKo&N0RuILvLrp~O)o"
    "x*H*aA%|}ClC~bM2f@)S)Nd=1rw5(V|nC|l$MKpUb<hK)>GSdKWl3*L%oTGAy5))n4DC`U`kll<%UclKv8$JDGg*"
    "5HY*ppGWR!a?`c)~^wT3`!i95TSKTtiVh`!Nf)bv(l-O8ExSk$Mbl|RWcrzkvLwna9>+8eBibQjwke0S~x&&gm^e"
    "EPj3ZGix)gf;tY@rQr8E+`T{c`@T+}`-_OZr$-AsOIFn<lW31Y)%}45ca9Ik%E3FGt{!0~^x5(6e^tx;Jgs`ia^n"
    "M1eM;l)xXxV=(?C<;Y+wtz?WsE;Is;KL4(S{^5!St2O+3%~uM~6ipJ!5Fso^47?8|3Jc`Zm|KTQn7k2S`*${0!6("
    "v9^y#-Y-bOUM8^%)slM{n8YL`Ie8hd0#>SN9cagrVtnaTc~;eTO=Y1{qY{58QMwTVg%Qi8*b2n&^}(+pys<ea6NI"
    "V1m?yncHe2jAb+Y(@NJ)g<e7YMY7q50u56$rMZ(OGpoBszDGONP|y}SJo<{@PCiP5qoj|K%atsqpRf{HSzWoQX`r"
    "sEWu$}U|0g5G{=ynFfT;PupucvZhX0S{6G8s>L5U0{+hSm)b^>~;6!q363|4=4FnHJm=ePhB(M-5*#bKpAIGwP!+"
    "0a^_f6*(sM{BeUPlZwSOf?kkb^@&gCK?yjX45A)F#D5Tbmrmw7(Q=awN32UA&$lq1LmbH<5>ss(4Be_6lm3B&nl5"
    "Kw-%>)-ZF190fJ7cU*`3=&q0XQ62C*$3|}>%bjvqTa?-uOqc}6c7!8KrFPZ`WfMGHx^BXp4W-;oX@2EOr;D{n`(*"
    "Fus4?j?ZHa!E^N*iGvBByWB90s+e*T9+epgoO8Q$;L?>=9ko2#?muHS#Y`gCzsk3KnW;DH2K&-L_2nUz~nZ}QGTe"
    "QHBJ<(G5o>?<h2!W$O7kMx=rb+5;Tn~TsjojZGS?A-9@H}jeb^5VRi|5|9OteUP>iA8G|bxZD80&!fY#06>ZwycA"
    "RbZ>2i_b6kqdm1aGI0Rf~Ssm=)P^5%whiMwNMZP>9Nhpu)i8NiMIyr5N;-*gur89c};p2zjer|0!nH<Za2D_xI-N"
    "mwUizs9U8WyK(oOW{;1rxJ5T$txoYdevSy13b@%*k=`v0q?=UTk$~gUyB(!DdHywH12Y*aSb<$0!;PUvKoCU3~hC"
    "K3recOL63Q<iIx!>%ng~9O>-cCA$9n`_=hH^Fr29%TEUTTa6R;sp{msS^jR4eFj{2W%NC(?sE{81*EZA34!h|>Ry"
    "~$EkIc-$(L7?5(4&2hYmqmqAFPJcAqwQCVB`{Qo^suba<KgiT|qLb;1>MTB#VyK!X#P(m2+N5~-5JLMEEVg1W?bF"
    "R7svvLmLMr8E{K_81DZ{{t;=LT>"
)


class StockSkillCiHelperTests(unittest.TestCase):
    @staticmethod
    def _stage3_review_task_ids(task_graph: str) -> tuple[str, ...]:
        result: list[str] = []
        row = re.compile(
            r"^\| `(?P<task>BSS-S3-P3-T[0-9]{3})` "
            r"\| (?P<phase>[^|]+?) \|"
        )
        for line in task_graph.splitlines():
            match = row.match(line)
            if match and match.group("phase").strip().startswith(
                ("Review", "Re-review")
            ):
                result.append(match.group("task"))
        return tuple(result)

    @staticmethod
    def _stage3_acceptance_verifiers(
        acceptance: str,
    ) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}
        for line in acceptance.splitlines():
            if not line.startswith("| `ACC-S3-"):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            acceptance_id = cells[1].strip("`")
            result[acceptance_id] = tuple(
                re.findall(r"BSS-S3-P3-T[0-9]{3}", cells[4])
            )
        return result

    def _run(self, script: Path, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(script), "--repo-root", str(root)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    @staticmethod
    def _public_fixture(root: Path) -> Path:
        (root / "Stock_Skill").mkdir(parents=True)
        (root / "AGENTS.md").write_text("public rules\n", encoding="utf-8")
        (root / "README.md").write_text("public readme\n", encoding="utf-8")
        stock_readme = root / "Stock_Skill/README.md"
        stock_readme.write_text("public stock skills\n", encoding="utf-8")
        return stock_readme

    def test_unittest_runner_rejects_zero_case_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zero-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_empty.py").write_bytes(b"")
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("zero test cases", result.stderr)

    def test_stage3_acceptance_verifiers_equal_derived_review_sequence(
        self,
    ) -> None:
        review_ids = self._stage3_review_task_ids(
            BSS_TASK_GRAPH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            review_ids,
            (
                "BSS-S3-P3-T001",
                "BSS-S3-P3-T003",
                "BSS-S3-P3-T005",
                "BSS-S3-P3-T007",
                "BSS-S3-P3-T009",
                "BSS-S3-P3-T011",
                "BSS-S3-P3-T013",
                "BSS-S3-P3-T015",
                "BSS-S3-P3-T017",
                "BSS-S3-P3-T019",
                "BSS-S3-P3-T021",
                "BSS-S3-P3-T023",
                "BSS-S3-P3-T025",
            ),
        )
        verifiers = self._stage3_acceptance_verifiers(
            BSS_ACCEPTANCE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            tuple(verifiers),
            tuple(f"ACC-S3-{ordinal:03d}" for ordinal in range(1, 11)),
        )
        for acceptance_id, observed in verifiers.items():
            with self.subTest(acceptance_id=acceptance_id):
                self.assertEqual(observed, review_ids)

    def test_stage3_acceptance_verifier_omission_mutant_is_killed(self) -> None:
        source = BSS_ACCEPTANCE.read_text(encoding="utf-8")
        mutated = source.replace(
            "; `BSS-S3-P3-T009`",
            "",
            1,
        )
        self.assertNotEqual(source, mutated)
        review_ids = self._stage3_review_task_ids(
            BSS_TASK_GRAPH.read_text(encoding="utf-8")
        )
        verifiers = self._stage3_acceptance_verifiers(mutated)
        self.assertTrue(
            any(observed != review_ids for observed in verifiers.values())
        )

    def test_unittest_runner_reports_actual_positive_case_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-positive-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_one.py").write_text(
                "import unittest\n"
                "class OneTest(unittest.TestCase):\n"
                "    def test_one(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: 1 test case(s)", result.stdout)

    def test_unittest_runner_rejects_failing_case(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-failing-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_failure.py").write_text(
                "import unittest\n"
                "class FailureTest(unittest.TestCase):\n"
                "    def test_failure(self): self.fail('synthetic failure')\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAILED", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_FINE_GRAINED_PAT}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub fine-grained PAT", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!payload.txt: forbidden GitHub fine-grained PAT",
                result.stderr,
            )

    def test_public_safety_rejects_session_receipt_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "019f8eda" + "-8938-7be0-9d40-" + "e6062b91c909"
            )
            receipt.write_text(
                json.dumps({key: synthetic_identifier})
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session metadata",
                result.stderr,
            )

    def test_public_safety_rejects_session_receipt_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "019f8eda" + "-8938-7be0-9d40-" + "e6062b91c909"
            )
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "receipt.json",
                    json.dumps({key: synthetic_identifier}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!receipt.json: forbidden execution session metadata",
                result.stderr,
            )

    def test_public_safety_rejects_generic_session_object_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-object-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            receipt.write_text(
                json.dumps({"session": {"engine": "synthetic"}}) + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session metadata at $.session",
                result.stderr,
            )

    def test_public_safety_rejects_generic_session_object_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-object-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "execution.json",
                    json.dumps({"session": {"engine": "synthetic"}}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!execution.json: forbidden execution session metadata "
                "at $.session",
                result.stderr,
            )

    def test_public_safety_rejects_uuid_v4_execution_receipt_in_plain_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-v4-plain-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/execution.json"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            receipt.write_text(
                json.dumps({"receipt": synthetic_identifier}) + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden execution session identifier at $.receipt",
                result.stderr,
            )

    def test_public_safety_rejects_uuid_v4_execution_receipt_in_zip_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-v4-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "execution.json",
                    json.dumps({"receipt": synthetic_identifier}),
                )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!execution.json: forbidden execution session "
                "identifier at $.receipt",
                result.stderr,
            )

    def test_public_safety_allows_uuid_v4_request_id_and_public_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-public-v4-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            receipt = root / "Stock_Skill/public.json"
            synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
            receipt.write_text(
                json.dumps(
                    {
                        "request_id": synthetic_identifier,
                        "source_url": (
                            "https://example.com/public/"
                            + synthetic_identifier
                        ),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_safety_rejects_private_metadata_synonym_matrix(self) -> None:
        variants = (
            "provider_session",
            "agent_session",
            "chat_session",
            "dialog_session",
            "interaction_session",
            "conversation_metadata",
            "thread_metadata",
            "session_details",
            "execution_session_info",
            "model_session_id",
            "run_session_id",
            "provider_thread_id",
            "provider_response_id",
            "execution_trace_id",
            "executor_session",
            "agent_session_id",
            "session_context",
            "execution_metadata",
            "execution_id",
            "provider_session_id",
            "thread_info",
            "run_id",
            "turn_uuid",
            "session_info",
            "execution_session_metadata",
            "model_session",
            "run_session",
            "session_state",
            "executor_receipt",
            "execution_record",
            "conversation_id",
            "thread_id",
            "chat_id",
            "turn_id",
            "execution_context",
            "agent_run",
            "conversation",
        )
        for surface in ("plain", "zip"):
            for key in variants:
                with self.subTest(surface=surface, key=key):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-private-metadata-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: {"private": "synthetic"}})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            archive_path = root / "Stock_Skill/synthetic.zip"
                            with ZipFile(
                                archive_path,
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_rejects_opaque_runtime_identifier_family(self) -> None:
        variants = (
            "inference_id",
            "completion_id",
            "generation_id",
            "invocation_id",
            "process_id",
            "worker_id",
            "span_id",
            "trace_id",
            "call_id",
            "job_id",
            "attempt_id",
            "request_context",
            "provider_token",
            "provider_correlation",
            "runtime_id",
            "runtime_receipt",
            "runtime_metadata",
            "runtime_uuid",
            "execution_token",
            "request_token",
            "provider_run_handle",
            "execution_attempt_handle",
            "job_handle",
        )
        synthetic_identifier = "123e4567-e89b-42d3-a456-426614174000"
        for surface in ("plain", "zip"):
            for key in variants:
                with self.subTest(surface=surface, key=key):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-opaque-runtime-id-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: synthetic_identifier})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_allows_public_business_identifier_controls(self) -> None:
        synthetic_uuid = (
            "550e8400" + "-e29b-41d4-a716-" + "446655440000"
        )
        controls = {
            "public_claim_ref": "CLAIM-001",
            "evidence_record_key": "EV-001",
            "research_case_ref": "CASE-001",
            "listed_issuer_name": "Example Issuer",
            "listed_security_symbol": "EXM",
            "global_benchmark_label": "Example Global Index",
            "public_source_uri": "https://example.invalid/source",
            "publication_date": "2026-07-24",
            "analysis_as_of": "2026-07-24",
            "research_cutoff": "2026-07-24",
            "horizon_month_count": 24,
            "bottleneck_score": 72.5,
            "investment_decision": "WATCHLIST",
            "valuation_metric": "EV/EBITDA",
            "proposed_weight": 0.0,
            "portfolio_risk_bucket": "medium",
            "public_request_ref": "REQ-PUBLIC-001",
            "request_public_reference": "public-request-20260724",
            "artifact_schema_version": "1.0",
            "remediation_task_id": "BSS-S3-P3-T022",
            "content_digest_sha256": "a" * 64,
            "execution_trace": {
                "validator_replay": {
                    "evidence": {
                        "result": {"claims": [{"id": synthetic_uuid}]}
                    }
                }
            },
            "runtime": {
                "market_observation": {
                    "publicEvidenceReference": "Evidence-Market-17"
                }
            },
            "executor_validator_replay": {
                "first_attempt_python_alias_missing_exit_code": 1
            },
        }
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-public-business-controls-"
                ) as raw:
                    root = Path(raw)
                    self._public_fixture(root)
                    payload = json.dumps(controls)
                    if surface == "plain":
                        (root / "Stock_Skill/public.json").write_text(
                            payload + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("public.json", payload)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )

    def test_public_safety_rejects_split_runtime_metadata_paths(self) -> None:
        payloads = (
            {"provider": {"token": "opaque-provider-token"}},
            {"runtime": {"receipt": {"token": "opaque-runtime-token"}}},
            {"execution": [{"handle": "opaque-execution-handle"}]},
            {"job": {"correlation": "opaque-job-correlation"}},
            {"trace": {"token": "opaque-trace-token"}},
            {"request": {"metadata": {"token": "opaque-request-token"}}},
            {
                "request_public_reference": (
                    "123e4567-e89b-42d3-a456-426614174000"
                )
            },
            {"request_public_reference": {"token": "private"}},
        )
        for surface in ("plain", "zip"):
            for payload in payloads:
                with self.subTest(surface=surface, payload=payload):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-split-runtime-metadata-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        encoded = json.dumps(payload)
                        if surface == "plain":
                            (root / "Stock_Skill/execution.json").write_text(
                                encoded + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", encoded)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_rejects_t015_blind_private_semantics(self) -> None:
        payloads = (
            {"providerExecutionLocator": "opaque-provider-locator"},
            {"job_trace_cursor": "opaque-job-cursor"},
            {"modelRunLocator": ["opaque-model-run-locator"]},
            {"TRACE\u00a0JOB\u00a0CURSOR": "opaque-nbsp-cursor"},
            {"runtimeJob": {"entries": [{"cursor": "opaque-cursor"}]}},
            {
                "trace": {
                    "batches": [
                        {"provider": {"alias": "opaque-provider-alias"}}
                    ]
                }
            },
            {
                "job": {
                    "records": [
                        {"request": {"locator": "opaque-request-locator"}}
                    ]
                }
            },
            {
                "execution": {
                    "audit": {
                        "trail": {"locator": "opaque-execution-locator"}
                    }
                }
            },
            {
                "provider": {
                    "envelope": {
                        "id": "630eb68f-e0fa-5ecc-887a-7c7a62614681"
                    }
                }
            },
            {
                "runtime": {
                    "wrapper": {
                        "payload": {"cursor": "opaque-runtime-cursor"}
                    }
                }
            },
            {
                "job": {
                    "events": [
                        {
                            "envelope": {
                                "locator": "opaque-job-event-locator"
                            }
                        }
                    ]
                }
            },
            {
                "trace": {
                    "containers": [
                        {"data": {"alias": "opaque-trace-alias"}}
                    ]
                }
            },
            {
                "provider": {
                    "items": [
                        {
                            "record": {
                                "id": (
                                    "c87ee674-4ddc-5d34-bc3f-"
                                    "b3db78e9e3a0"
                                )
                            }
                        }
                    ]
                }
            },
            {
                "execution": {
                    "batches": [
                        {"trail": {"handle": "opaque-execution-handle"}}
                    ]
                }
            },
        )
        for surface in ("plain", "zip"):
            for payload in payloads:
                with self.subTest(surface=surface, payload=payload):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t015-private-semantics-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        encoded = json.dumps(payload)
                        if surface == "plain":
                            (root / "Stock_Skill/execution.json").write_text(
                                encoded + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", encoded)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session",
                            result.stderr,
                        )

    def test_public_safety_allows_descriptive_public_request_reference(self) -> None:
        payload = {
            "publicResearchRequestReference": (
                "public-transformer-request-20260724"
            )
        }
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-public-research-reference-"
                ) as raw:
                    root = Path(raw)
                    self._public_fixture(root)
                    encoded = json.dumps(payload)
                    if surface == "plain":
                        (root / "Stock_Skill/public.json").write_text(
                            encoded + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("public.json", encoded)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )

    def test_public_safety_rejects_t017_structural_private_ancestry(self) -> None:
        payloads = (
            {"provider": {"pages": [{"cursor": "opaque-provider-cursor"}]}},
            {"runtime": {"segments": [{"locator": "opaque-runtime-locator"}]}},
            {"execution": {"nodes": [{"alias": "opaque-execution-alias"}]}},
            {"job": {"list": [{"locator": "opaque-job-locator"}]}},
            {"trace": {"array": [{"cursor": "opaque-trace-cursor"}]}},
            {"provider": {"collection": [{"handle": "opaque-provider-handle"}]}},
        )
        for surface in ("plain", "zip"):
            for payload in payloads:
                with self.subTest(surface=surface, payload=payload):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t017-structural-ancestry-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        encoded = json.dumps(payload)
                        if surface == "plain":
                            (root / "Stock_Skill/execution.json").write_text(
                                encoded + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", encoded)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session metadata",
                            result.stderr,
                        )

    def test_public_safety_allows_t017_public_reference_controls(self) -> None:
        controls = {
            "public_request_alias": "public-request-alias",
            "public_documentation_locator": "public-documentation-locator",
            "public_evidence_cursor": "public-evidence-cursor",
            "public_catalog_reference": "public-catalog-reference",
            "public_example_alias": "public-example-alias",
        }
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-t017-public-reference-"
                ) as raw:
                    root = Path(raw)
                    self._public_fixture(root)
                    encoded = json.dumps(controls)
                    if surface == "plain":
                        (root / "Stock_Skill/public.json").write_text(
                            encoded + "\n",
                            encoding="utf-8",
                        )
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("public.json", encoded)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )

    def test_public_safety_rejects_t017_malformed_public_reference_controls(
        self,
    ) -> None:
        keys = (
            "public_request_alias",
            "public_documentation_locator",
            "public_evidence_cursor",
            "public_catalog_reference",
            "public_example_alias",
        )
        invalid_values = (
            "123e4567-e89b-42d3-a456-426614174000",
            {"token": "private"},
        )
        for surface in ("plain", "zip"):
            for key in keys:
                for value in invalid_values:
                    with self.subTest(surface=surface, key=key, value=value):
                        with tempfile.TemporaryDirectory(
                            prefix="stock-ci-t017-malformed-public-reference-"
                        ) as raw:
                            root = Path(raw)
                            self._public_fixture(root)
                            encoded = json.dumps({key: value})
                            if surface == "plain":
                                (
                                    root / "Stock_Skill/public.json"
                                ).write_text(
                                    encoded + "\n",
                                    encoding="utf-8",
                                )
                            else:
                                with ZipFile(
                                    root / "Stock_Skill/synthetic.zip",
                                    "w",
                                    compression=ZIP_DEFLATED,
                                ) as archive:
                                    archive.writestr("public.json", encoded)
                            result = self._run(SAFETY_VALIDATOR, root)
                            self.assertNotEqual(
                                result.returncode,
                                0,
                                result.stdout + result.stderr,
                            )
                            self.assertIn(
                                "forbidden execution session metadata",
                                result.stderr,
                            )

    def test_public_safety_rejects_provider_session_identifier_in_text_surfaces(
        self,
    ) -> None:
        key = "provider" + "_" + "session" + "_" + "id"
        identifier = "123e4567" + "-e89b-42d3-a456-" + "426614174000"
        marker = f"{key}={identifier}"
        for surface in ("plain", "zip"):
            with self.subTest(surface=surface):
                with tempfile.TemporaryDirectory(
                    prefix="stock-ci-t017-provider-session-text-"
                ) as raw:
                    root = Path(raw)
                    stock_readme = self._public_fixture(root)
                    if surface == "plain":
                        stock_readme.write_text(marker + "\n", encoding="utf-8")
                    else:
                        with ZipFile(
                            root / "Stock_Skill/synthetic.zip",
                            "w",
                            compression=ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr("execution.txt", marker)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )
                    self.assertIn(
                        "forbidden plaintext execution session identifier",
                        result.stderr,
                    )

    def test_public_safety_rejects_t019_plaintext_identifier_matrix(
        self,
    ) -> None:
        identifier = "550e8400" + "-e29b-41d4-a716-" + "446655440000"
        prefixes = (
            "provider.session." + "id = ",
            "provider-session-" + "id: ",
            "Provider Session " + "Identifier -> ",
            "providerSession" + "Id ",
            "runtime request " + "locator: ",
            "generation.execution." + "cursor/",
        )
        for surface in ("plain", "zip"):
            for prefix in prefixes:
                with self.subTest(surface=surface, prefix=prefix):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t019-private-text-"
                    ) as raw:
                        root = Path(raw)
                        stock_readme = self._public_fixture(root)
                        marker = prefix + identifier
                        if surface == "plain":
                            stock_readme.write_text(
                                marker + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.txt", marker)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden plaintext execution session identifier",
                            result.stderr,
                        )

    def test_public_safety_t022_blind_matrix_plain_and_zip(self) -> None:
        identifier = "550e8400" + "-e29b-41d4-a716-" + "446655440000"
        negative_plaintext = (
            ("NP01", f"inference.request.id = {identifier}"),
            ("NP02", f"completion-session-identifier: {identifier}"),
            ("NP03", f"Invocation Context ID -> {identifier}"),
            ("NP04", f"process.execution.cursor / {identifier}"),
            ("NP05", f"worker run locator {identifier}"),
            ("NP06", f"span.receipt.id={identifier}"),
            ("NP07", f"trace-session-state:{identifier}"),
            ("NP08", f"call execution record -> {identifier}"),
            ("NP09", f"job.request.metadata {identifier}"),
            ("NP10", f"task-runtime-handle = {identifier}"),
            ("NP11", f"pipeline invocation receipt: {identifier}"),
            ("NP12", f"response generation identifier / {identifier}"),
        )
        negative_json = (
            ("NJ01", {"inference": {"records": [{"cursor": identifier}]}}),
            ("NJ02", {"completion": {"pages": [{"locator": identifier}]}}),
            ("NJ03", {"invocation": {"items": [{"receipt": identifier}]}}),
            ("NJ04", {"worker": {"nodes": [{"handle": "opaque-worker-handle"}]}}),
            ("NJ05", {"trace": {"segments": [{"state": identifier}]}}),
            (
                "NJ06",
                {"runtime": {"market_observation": {"session_id": identifier}}},
            ),
            (
                "NJ07",
                {
                    "execution_trace": {
                        "validator_replay": {"provider_receipt": identifier}
                    }
                },
            ),
            (
                "NJ08",
                {
                    "runtime": {
                        "market_observation": {
                            "provider": {"session": {"id": identifier}}
                        }
                    }
                },
            ),
            (
                "NJ09",
                {
                    "execution_trace": {
                        "validator_replay": {"job": {"cursor": identifier}}
                    }
                },
            ),
            (
                "NJ10",
                {
                    "pipeline": {
                        "collections": [
                            {"request_identifier": identifier}
                        ]
                    }
                },
            ),
        )
        positive_plaintext = (
            ("PP01", f"public evidence record: {identifier}"),
            ("PP02", f"market observation id = {identifier}"),
            ("PP03", f"public dataset row / {identifier}"),
            ("PP04", f"claim evidence identifier -> {identifier}"),
        )
        positive_json = (
            (
                "PJ01",
                {"runtime": {"market_observation": {"observation_id": identifier}}},
            ),
            (
                "PJ02",
                {
                    "execution_trace": {
                        "validator_replay": {
                            "evidence": {"claim_id": identifier}
                        }
                    }
                },
            ),
            (
                "PJ03",
                {
                    "runtime": {
                        "market_observation": {
                            "source_registry": {"record_uuid": identifier}
                        }
                    }
                },
            ),
            (
                "PJ04",
                {
                    "execution_trace": {
                        "validator_replay": {
                            "public_dataset": {"rows": [{"id": identifier}]}
                        }
                    }
                },
            ),
            ("PJ05", {"evidence": {"claims": [{"id": identifier}]}}),
            ("PJ06", {"public_catalog_reference": "Grid-Evidence-2026-07"}),
        )
        groups = (
            ("negative_plaintext", True, ".txt", negative_plaintext),
            ("negative_json", True, ".json", negative_json),
            ("positive_plaintext", False, ".txt", positive_plaintext),
            ("positive_json", False, ".json", positive_json),
        )
        for category, expected_reject, suffix, cases in groups:
            for case_id, value in cases:
                payload = (
                    json.dumps(value, ensure_ascii=False)
                    if suffix == ".json"
                    else value
                )
                for surface in ("plain", "zip"):
                    with self.subTest(
                        category=category,
                        case_id=case_id,
                        surface=surface,
                    ):
                        with tempfile.TemporaryDirectory(
                            prefix="stock-ci-t022-public-blind-"
                        ) as raw:
                            root = Path(raw)
                            self._public_fixture(root)
                            if surface == "plain":
                                (root / f"Stock_Skill/probe{suffix}").write_text(
                                    payload + "\n",
                                    encoding="utf-8",
                                )
                            else:
                                with ZipFile(
                                    root / "Stock_Skill/synthetic.zip",
                                    "w",
                                    compression=ZIP_DEFLATED,
                                ) as archive:
                                    archive.writestr(f"probe{suffix}", payload)
                            result = self._run(SAFETY_VALIDATOR, root)
                            if expected_reject:
                                self.assertNotEqual(
                                    result.returncode,
                                    0,
                                    result.stdout + result.stderr,
                                )
                                self.assertIn(
                                    (
                                        "forbidden plaintext execution "
                                        "session identifier"
                                        if suffix == ".txt"
                                        else "forbidden execution session"
                                    ),
                                    result.stderr,
                                )
                            else:
                                self.assertEqual(
                                    result.returncode,
                                    0,
                                    result.stdout + result.stderr,
                                )

    def test_public_safety_t022_handle_rollback_mutant_is_killed(self) -> None:
        source = SAFETY_VALIDATOR.read_text(encoding="utf-8")
        new_detail_tail = "           context|record|run|handle)"
        self.assertEqual(source.count(new_detail_tail), 1)
        mutant = source.replace(
            new_detail_tail,
            "           context|record|run)",
            1,
        )
        with tempfile.TemporaryDirectory(
            prefix="stock-ci-t022-public-rollback-"
        ) as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            identifier = (
                "550e8400" + "-e29b-41d4-a716-" + "446655440000"
            )
            stock_readme.write_text(
                f"task-runtime-handle = {identifier}\n",
                encoding="utf-8",
            )
            mutant_validator = root / "mutant_public_safety.py"
            mutant_validator.write_text(mutant, encoding="utf-8")
            result = self._run(mutant_validator, root)
            self.assertEqual(
                result.returncode,
                0,
                "rollback mutant unexpectedly retained the T022 defense",
            )

    def test_public_safety_t024_frozen_replay_plain_and_zip(self) -> None:
        raw_oracle = zlib.decompress(
            base64.b85decode(T024_PUBLIC_SAFETY_REPLAY_B85.encode("ascii"))
        )
        self.assertEqual(
            hashlib.sha256(raw_oracle).hexdigest(),
            "64b6deeee0311ef6c08b07eaff46e77f85dc1c3188ed980a9e852cce69584bfb",
        )
        oracle = json.loads(raw_oracle.decode("utf-8"))
        self.assertEqual(oracle["schema"], "bss-t024-public-safety-replay-v1")
        self.assertEqual(
            oracle["specialist_artifact_sha256"],
            "fa9584ea88397bc09eb233a8217899d11eb362e9cff72c224904a4d223613f0b",
        )
        self.assertEqual(
            oracle["adjacent_artifact_sha256"],
            "b3ebe869874c80b1992e2875c798f3421f82fcdda6b8876de683992f04f3df8b",
        )
        self.assertEqual(len(oracle["cases"]), 86)
        for case in oracle["cases"]:
            payload = (
                json.dumps(
                    case["value"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if case["kind"] == "json"
                else str(case["value"])
            )
            suffix = ".json" if case["kind"] == "json" else ".txt"
            expected_reject = case["expected"] == "REJECT"
            for surface in ("plain", "zip"):
                with self.subTest(case_id=case["id"], surface=surface):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t024-public-replay-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        if surface == "plain":
                            (root / f"Stock_Skill/probe{suffix}").write_text(
                                payload + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr(f"probe{suffix}", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                    if expected_reject:
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            (
                                "forbidden execution session"
                                if suffix == ".json"
                                else (
                                    "forbidden plaintext execution "
                                    "session identifier"
                                )
                            ),
                            result.stderr,
                        )
                    else:
                        self.assertEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )

    def test_public_safety_t024_fresh_cross_product_plain_and_zip(self) -> None:
        cases = (
            (
                "R21",
                True,
                ".json",
                {
                    "invocation": {
                        "chunks": [
                            {
                                "context": {
                                    "cursor": "invocation-opaque-private-10"
                                }
                            }
                        ]
                    }
                },
            ),
            (
                "R22",
                True,
                ".json",
                {
                    "inference": {
                        "frames": [
                            {
                                "private": {
                                    "alias": "inference-opaque-private-11"
                                }
                            }
                        ]
                    }
                },
            ),
            (
                "R23",
                True,
                ".json",
                {
                    "orchestration": {
                        "custom": {
                            "pointer": "orchestration-opaque-private-12"
                        }
                    }
                },
            ),
            (
                "R24",
                True,
                ".json",
                {"execution": {"task": {"id": "RUN-PRIVATE-17"}}},
            ),
            (
                "R25",
                True,
                ".json",
                {"runtime_task_id": "RUN-PRIVATE-17"},
            ),
            (
                "R26",
                True,
                ".txt",
                "pipeline context handle " + "abcdefghijklmnop",
            ),
            (
                "R27",
                True,
                ".json",
                {
                    "runtime": {
                        "cases": {
                            "custom": {
                                "cursor": "runtime-opaque-private-77"
                            }
                        }
                    }
                },
            ),
            (
                "R28",
                True,
                ".json",
                {
                    "runtime": {
                        "public_wrapper": {
                            "custom": {
                                "cursor": "runtime-opaque-private-78"
                            }
                        }
                    }
                },
            ),
            (
                "R29",
                True,
                ".json",
                {
                    "pipeline": {
                        "public_task": {
                            "id": "RUN-PRIVATE-17"
                        }
                    }
                },
            ),
            (
                "R30",
                True,
                ".txt",
                "pipeline context handle " + "deadbeefdeadbeef",
            ),
            (
                "R31",
                True,
                ".txt",
                "pipeline context handle " + "xqjpvnmzlkxqjpvn",
            ),
            (
                "R32",
                True,
                ".txt",
                "pipeline context handle " + "deadbeefdeadbeef.",
            ),
            (
                "R33",
                True,
                ".txt",
                "pipeline context handle " + "xqjpvnmzlkxqjpvn:",
            ),
            (
                "R34",
                True,
                ".txt",
                "pipeline context handle " + "xqjpvnmzlkxqjpvn!",
            ),
            (
                "A13",
                False,
                ".json",
                {"task": {"id": "SEC-2024-17"}},
            ),
            (
                "A14",
                False,
                ".json",
                {"pipeline": {"public_task": {"id": "ADP-SOURCE-17"}}},
            ),
            (
                "A15",
                False,
                ".txt",
                "Runtime state misconfiguration caused the warning.",
            ),
            (
                "A16",
                False,
                ".txt",
                "Execution record misclassification caused the warning.",
            ),
            (
                "A17",
                False,
                ".txt",
                "Pipeline state mischaracterization remains a risk.",
            ),
            (
                "A18",
                False,
                ".txt",
                "Task state internationalization is documented.",
            ),
            (
                "A19",
                False,
                ".txt",
                "Runtime state misconfiguration",
            ),
            (
                "A20",
                False,
                ".txt",
                "Runtime state internationalization, with notes.",
            ),
        )
        for case_id, expected_reject, suffix, value in cases:
            payload = (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if suffix == ".json"
                else str(value)
            )
            for surface in ("plain", "zip"):
                with self.subTest(case_id=case_id, surface=surface):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-t024-public-fresh-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        if surface == "plain":
                            (root / f"Stock_Skill/probe{suffix}").write_text(
                                payload + "\n",
                                encoding="utf-8",
                            )
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr(f"probe{suffix}", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                    if expected_reject:
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            (
                                "forbidden plaintext execution session"
                                if suffix == ".txt"
                                else "forbidden execution session"
                            ),
                            result.stderr,
                        )
                    else:
                        self.assertEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )

    def test_public_safety_t024_opaque_ancestry_rollback_mutant_is_killed(
        self,
    ) -> None:
        source = SAFETY_VALIDATOR.read_text(encoding="utf-8")
        opaque_value_guard = (
            "            (?=[a-z0-9._@%+#=/~-]{8,128}\n"
            "               (?![a-z0-9._@%+#=/~-]))"
        )
        self.assertEqual(source.count(opaque_value_guard), 1)
        mutant = source.replace(
            opaque_value_guard,
            "        (?!)",
            1,
        )
        with tempfile.TemporaryDirectory(
            prefix="stock-ci-t024-public-rollback-"
        ) as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                "pipeline context handle "
                + "pipeline-opaque-private-review-32\n",
                encoding="utf-8",
            )
            mutant_validator = root / "mutant_public_safety.py"
            mutant_validator.write_text(mutant, encoding="utf-8")
            result = self._run(mutant_validator, root)
            self.assertEqual(
                result.returncode,
                0,
                "rollback mutant unexpectedly retained opaque-ID defense",
            )

    def test_public_safety_t024_generic_ancestry_rollback_mutant_is_killed(
        self,
    ) -> None:
        source = SAFETY_VALIDATOR.read_text(encoding="utf-8")
        generic_ancestry = "                elif isinstance(child, (dict, list)):"
        self.assertEqual(source.count(generic_ancestry), 1)
        mutant = source.replace(
            generic_ancestry,
            "                elif is_neutral_context_container(key, child):",
            1,
        )
        with tempfile.TemporaryDirectory(
            prefix="stock-ci-t024-public-ancestry-rollback-"
        ) as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "invocation": {
                            "chunks": [
                                {
                                    "context": {
                                        "cursor": "invocation-opaque-private-10"
                                    }
                                }
                            ]
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            mutant_validator = root / "mutant_public_safety.py"
            mutant_validator.write_text(mutant, encoding="utf-8")
            result = self._run(mutant_validator, root)
            self.assertEqual(
                result.returncode,
                0,
                "rollback mutant unexpectedly retained generic ancestry",
            )

    def test_public_safety_t024_runtime_task_rollback_mutant_is_killed(
        self,
    ) -> None:
        source = SAFETY_VALIDATOR.read_text(encoding="utf-8")
        runtime_guard = "        and not bool(combined & private_runtime_tokens)\n"
        self.assertEqual(source.count(runtime_guard), 1)
        mutant = source.replace(runtime_guard, "", 1)
        with tempfile.TemporaryDirectory(
            prefix="stock-ci-t024-public-task-rollback-"
        ) as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.with_suffix(".json").write_text(
                json.dumps(
                    {"execution": {"task": {"id": "RUN-CONTROL-17"}}}
                )
                + "\n",
                encoding="utf-8",
            )
            mutant_validator = root / "mutant_public_safety.py"
            mutant_validator.write_text(mutant, encoding="utf-8")
            result = self._run(mutant_validator, root)
            self.assertEqual(
                result.returncode,
                0,
                "rollback mutant unexpectedly retained runtime-task defense",
            )

    def test_public_safety_t024_alpha_opaque_rollback_mutant_is_killed(
        self,
    ) -> None:
        source = SAFETY_VALIDATOR.read_text(encoding="utf-8")
        alpha_shape = "            (?P<alpha_opaque>[a-z]{16,128})\n"
        self.assertEqual(source.count(alpha_shape), 1)
        mutant = source.replace(alpha_shape, "            (?!)\n", 1)
        with tempfile.TemporaryDirectory(
            prefix="stock-ci-t024-public-alpha-rollback-"
        ) as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                "pipeline context handle " + "abcdefghijklmnop\n",
                encoding="utf-8",
            )
            mutant_validator = root / "mutant_public_safety.py"
            mutant_validator.write_text(mutant, encoding="utf-8")
            result = self._run(mutant_validator, root)
            self.assertEqual(
                result.returncode,
                0,
                "rollback mutant unexpectedly retained alphabetic opaque-ID defense",
            )

    def test_public_safety_rejects_private_identifier_under_runtime_key(self) -> None:
        variants = (
            ("execution", "123e4567-e89b-42d3-a456-426614174000"),
            ("execution", "sess_live_synthetic_123"),
            ("executor_id", "sess_live_synthetic_123"),
        )
        for surface in ("plain", "zip"):
            for key, value in variants:
                with self.subTest(surface=surface, key=key, value=value):
                    with tempfile.TemporaryDirectory(
                        prefix="stock-ci-private-runtime-id-"
                    ) as raw:
                        root = Path(raw)
                        self._public_fixture(root)
                        payload = json.dumps({key: value})
                        if surface == "plain":
                            (
                                root / "Stock_Skill/execution.json"
                            ).write_text(payload + "\n", encoding="utf-8")
                        else:
                            with ZipFile(
                                root / "Stock_Skill/synthetic.zip",
                                "w",
                                compression=ZIP_DEFLATED,
                            ) as archive:
                                archive.writestr("execution.json", payload)
                        result = self._run(SAFETY_VALIDATOR, root)
                        self.assertNotEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                        self.assertIn(
                            "forbidden execution session identifier",
                            result.stderr,
                        )

    def test_public_safety_rejects_plaintext_session_identifier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-session-text-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            key = "session" + "_" + "id"
            synthetic_identifier = (
                "123e4567" + "-e89b-42d3-a456-" + "426614174000"
            )
            stock_readme.write_text(
                f"{key}={synthetic_identifier}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "forbidden plaintext execution session identifier",
                result.stderr,
            )

    def test_public_safety_allows_declared_boolean_execution_controls(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-safe-controls-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            control = root / "Stock_Skill/control.json"
            control.write_text(
                json.dumps(
                    {
                        "fresh_ephemeral_session": True,
                        "conversation_history_forwarded": False,
                        "request_id": "public-request-001",
                        "execution_controls": {"network_allowed": False},
                        "execution_provenance": {"executor": "synthetic-host"},
                        "executor_id": "forward-executor-t002",
                        "execution_receipt_sha256": "a" * 64,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_safety_rejects_nonboolean_safe_control_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-control-shape-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            control = root / "Stock_Skill/control.json"
            control.write_text(
                json.dumps({"fresh_ephemeral_session": {"id": "private"}})
                + "\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "malformed public execution control",
                result.stderr,
            )

    def test_public_safety_rejects_windows_style_zip_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-path-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            for name in (
                "..\\escape.txt",
                "C:\\escape.txt",
                "C:/escape.txt",
                "\\\\server\\share\\escape.txt",
                "folder\\file.txt",
            ):
                with self.subTest(name=name):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr(name, "benign")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unsafe ZIP path", result.stderr)

    def test_public_safety_rejects_nonempty_zip_directory_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-dir-payload-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            directory = ZipInfo("concealed/")
            directory.compress_type = ZIP_DEFLATED
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(directory, SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty directory ZIP entry", result.stderr)

    def test_public_safety_allows_empty_zip_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-empty-dir-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("empty/", b"")
                archive.writestr("empty/payload.txt", "benign")
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("1 ZIP entries", result.stdout)

    def test_public_safety_rejects_stateless_app_token_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_STATELESS_APP_TOKEN}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_stateless_app_token_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_STATELESS_APP_TOKEN)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_bare_and_child_user_home_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-bare-home-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            mac_root = "/" + "Users/"
            mac_case_root = "/" + "users/"
            linux_root = "/" + "home/"
            windows_root = "C:" + "\\" + "Users\\"
            windows_case_root = "c:" + "\\" + "users\\"
            windows_forward_case_root = "c:" + "/" + "users/"
            ascii_user = "exampleuser"
            unicode_user = "测试用户"
            cases = (
                ("macOS user path", mac_root + ascii_user),
                ("macOS user path", mac_root + ascii_user + "/project"),
                ("macOS user path", mac_case_root + ascii_user),
                ("macOS user path", mac_root + unicode_user),
                ("Linux user path", linux_root + ascii_user),
                ("Linux user path", linux_root + ascii_user + "/project"),
                ("Linux user path", linux_root + unicode_user),
                ("Windows user path", windows_root + ascii_user),
                ("Windows user path", windows_root + ascii_user + "\\project"),
                ("Windows user path", windows_case_root + ascii_user),
                ("Windows user path", windows_forward_case_root + ascii_user),
                ("Windows user path", windows_root + unicode_user),
            )
            for pattern_name, value in cases:
                with self.subTest(pattern_name=pattern_name):
                    stock_readme.write_text(value + "\n", encoding="utf-8")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"forbidden {pattern_name}", result.stderr)

    def test_public_safety_rejects_case_and_unicode_user_homes_in_zip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-home-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            values = (
                "/" + "users/" + "exampleuser",
                "c:" + "\\" + "users\\" + "exampleuser",
                "c:" + "/" + "users/" + "exampleuser",
                "/" + "Users/" + "测试用户",
                "/" + "home/" + "测试用户",
                "C:" + "\\" + "Users\\" + "测试用户",
            )
            for value in values:
                with self.subTest(value=value):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", value)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("forbidden", result.stderr)

    def test_public_safety_allows_ellipsis_path_placeholder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-path-placeholder-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            placeholders = (
                "/" + "Users/" + "...",
                "/" + "users/" + "…",
                "/" + "home/" + "...",
                "C:" + "\\" + "Users\\" + "...",
            )
            for placeholder in placeholders:
                with self.subTest(placeholder=placeholder):
                    stock_readme.write_text(
                        f"portable documentation placeholder: `{placeholder}`\n",
                        encoding="utf-8",
                    )
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )

    def test_public_safety_allows_public_url_with_home_path_segment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-public-home-url-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                "source: https://example.com/global/en/home/press-releases/item.html\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_historical_path_allowlist_is_exact_and_backticked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-path-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            exact_path = "/home/" + "oai/" + "skills"
            safe_boundaries = ("\n", ".\n", "；继续说明\n", ")\n")
            for boundary in safe_boundaries:
                with self.subTest(boundary=boundary):
                    stock_readme.write_text(
                        f"historical: `{exact_path}`{boundary}", encoding="utf-8"
                    )
                    passing = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        passing.returncode, 0, passing.stdout + passing.stderr
                    )
            stock_readme.write_text(
                f"unbackticked historical path: {exact_path}\n", encoding="utf-8"
            )
            unbackticked = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(unbackticked.returncode, 0)
            self.assertIn("forbidden Linux user path", unbackticked.stderr)
            stock_readme.write_text(
                f"historical file URI: `file://{exact_path}`\n", encoding="utf-8"
            )
            file_uri = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(file_uri.returncode, 0)
            self.assertIn("forbidden Linux user path", file_uri.stderr)
            stock_readme.write_text(
                f"historical child: `{exact_path}/private`\n", encoding="utf-8"
            )
            failing = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(failing.returncode, 0)
            self.assertIn("forbidden Linux user path", failing.stderr)

    def test_historical_path_allowlist_rejects_post_backtick_continuation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-boundary-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            exact_path = "/home/" + "oai/" + "skills"
            continuations = (
                "/private",
                "\\private",
                "suffix",
                "_suffix",
                "-suffix",
                "9",
                "测试",
                "@suffix",
            )
            for continuation in continuations:
                payload = f"`{exact_path}`{continuation}"
                with self.subTest(surface="plain", continuation=continuation):
                    if archive_path.exists():
                        archive_path.unlink()
                    stock_readme.write_text(payload + "\n", encoding="utf-8")
                    plain = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(plain.returncode, 0)
                    self.assertIn(
                        "Stock_Skill/README.md: forbidden Linux user path",
                        plain.stderr,
                    )
                with self.subTest(surface="zip", continuation=continuation):
                    stock_readme.write_text("public stock skills\n", encoding="utf-8")
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", payload)
                    zipped = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(zipped.returncode, 0)
                    self.assertIn(
                        "synthetic.zip!payload.txt: forbidden Linux user path",
                        zipped.stderr,
                    )


if __name__ == "__main__":
    unittest.main()
