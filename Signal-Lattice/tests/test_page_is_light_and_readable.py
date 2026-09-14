"""页面是白底，并且每一处文字都真的读得清。

Owner 的要求是「把页面改成白色的」。白底本身不难，难的是白底上沿用深色
主题的浅色文字——看起来是白页面，实际一个字都看不清。所以这里不只断言
「底色是白的」，而是把每一对「文字色 / 它所在的底色」按 WCAG 对比度算一遍。

另外把「颜色只能写在 :root」钉死：只要还有一处颜色写死在规则里，换主题
就必然漏掉那一处，上一轮的白色标题就是这么来的。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

ROOT_BLOCK = STYLES[STYLES.index(":root{") : STYLES.index("}", STYLES.index(":root{"))]
BODY = STYLES[STYLES.index("}", STYLES.index(":root{")) + 1 :]
TOKENS = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", ROOT_BLOCK))

# 正文 4.5:1；页面上没有大到可以走 3:1 豁免的正文。
MINIMUM_CONTRAST = 4.5
# 文字 token -> 它实际所在的底色 token
TEXT_ON = {
    "text": ["surface", "bg", "surface-2"],
    "lead": ["surface"],
    "muted": ["surface", "bg", "surface-2"],
    "accent": ["surface", "bg"],
    "warning": ["surface", "bg"],
    "danger": ["surface", "bg"],
    "on-accent": ["accent-fill"],
    "on-warning": ["warning-fill"],
    "on-danger": ["danger-fill"],
}


def _channel(value: float) -> float:
    value /= 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[index : index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(foreground: str, background: str) -> float:
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class PageIsLightAndReadable(unittest.TestCase):
    def test_declares_a_light_colour_scheme(self):
        self.assertIn("color-scheme:light", STYLES)
        self.assertNotIn("color-scheme:dark", STYLES)
        self.assertIn('<meta name="color-scheme" content="light">', INDEX)

    def test_page_and_panels_are_white(self):
        for token in ("bg", "surface"):
            with self.subTest(token=token):
                self.assertGreater(luminance(TOKENS[token]), 0.85, f"--{token} 不是白底")

    def test_every_text_colour_is_readable_on_its_own_background(self):
        for foreground, backgrounds in TEXT_ON.items():
            for background in backgrounds:
                with self.subTest(fg=foreground, bg=background):
                    ratio = contrast(TOKENS[foreground], TOKENS[background])
                    self.assertGreaterEqual(
                        ratio,
                        MINIMUM_CONTRAST,
                        f"--{foreground} 在 --{background} 上只有 {ratio:.2f}:1",
                    )

    def test_no_colour_is_written_outside_the_token_block(self):
        stray = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", BODY)))
        self.assertEqual(stray, [], f"这些颜色写死在规则里，换主题必漏：{stray}")

    def test_every_fill_has_a_declared_text_colour(self):
        for fill in ("accent-fill", "warning-fill", "danger-fill"):
            with self.subTest(fill=fill):
                self.assertIn(fill, TOKENS)
                self.assertIn(f"on-{fill.removesuffix('-fill')}", TOKENS)


if __name__ == "__main__":
    unittest.main()
