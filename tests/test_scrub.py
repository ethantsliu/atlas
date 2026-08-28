import unittest

from pipeline.scrub import (
    has_locator,
    scrub_author,
    scrub_contact,
    scrub_paper,
    scrub_text,
    scrub_tree,
)


class ScrubTests(unittest.TestCase):
    def test_private_links(self) -> None:
        text = (
            "This increasedhttps://www.overleaf.com/project/"
            "5e2b14694c5dc600017292e6 intercorrelation. "
            "Remove www.overleaf.com/project/5e2b14694c5dc600017292e7 too. "
            "See https://twitter.com/example/status/1 and Twitter: @private_handle."
        )

        cleaned = scrub_text(text)

        self.assertEqual(
            cleaned,
            "This increased intercorrelation. Remove too. See "
            "https://twitter.com/example/status/1 and Twitter: @private_handle.",
        )
        self.assertFalse(has_locator(cleaned))
        self.assertEqual(scrub_text(cleaned), cleaned)

    def test_contact_paths(self) -> None:
        text = (
            "Contact author@example.org or PERSON@EXAMPLE.COM; open "
            "file:///tmp/note, /Users/alice/note, /home/alice/note, "
            "C:\\Users\\alice\\note, https://localhost/note, "
            "localhost:3000/private, 127.0.0.1:8000/private, "
            "[::1]:9000/private, or "
            "http://workstation.local/private, or "
            "https://alice:secret@example.org/private."
        )

        cleaned = scrub_text(text)

        for private in (
            "file://",
            "/Users/",
            "/home/",
            "C:\\",
            "localhost",
            "alice:secret",
        ):
            self.assertNotIn(private, cleaned)
        self.assertIn("author@example.org", cleaned)
        self.assertIn("PERSON@EXAMPLE.COM", cleaned)
        self.assertFalse(has_locator(cleaned))

    def test_unicode_paths(self) -> None:
        cases = (
            "Open ／Users／alice／note",
            "See https：／／localhost／private",
            "Read file：／／／tmp／private",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(has_locator(scrub_text(text)))
                self.assertNotEqual(scrub_text(text), text)

    def test_public_links(self) -> None:
        text = (
            "Read https://arxiv.org/abs/2401.00001, code at "
            "https://github.com/public-lab/public-paper, and data at "
            "https://idda-dataset.github.io/home/. MC@NLO, MUSE@VLT, "
            "KIT@BeTraC, and @300K remain scholarly notation. Public URL "
            "https://example.org/get?file=/home/archive/data.zip, public email "
            "researcher@example.org, and git@github.com:lab/code.git remain too."
        )

        self.assertEqual(scrub_text(text), text)
        self.assertFalse(has_locator(text))

    def test_host_boundary(self) -> None:
        text = (
            "Public http://localhost.example.org/paper remains available. "
            "So do http://foo.localhost/paper, http://foo.locality.org/paper, "
            "and http://foo.local.example.org/paper. "
            "When accessed from localhost, the ratio ν_τ::1 is unchanged."
        )

        self.assertEqual(scrub_text(text), text)
        self.assertFalse(has_locator(text))

    def test_scholarly_syntax(self) -> None:
        text = (
            r"SUSY@LHC.CERN.CH uses WFI@2.2m and @SUSY08 with ~\GeV, "
            r"~\vec{p}, ~\s, O(\barα~\barα_s), C:\alpha, \\mathcal{A}, "
            r"~/J_1, @AA, @VVV, @ApWeb, C_60@C_240, @CNT, @p97mm, "
            r"@Ar, @article, and @book. The exact arXiv forms \\m\in M and "
            r"\\n\odd remain mathematical notation. Adjacent commands "
            r"\\alpha\beta\gamma, \\mathrm\mathbf, and \\sum\limits remain."
        )

        self.assertEqual(scrub_text(text), text)
        self.assertFalse(has_locator(text))

    def test_unc_path(self) -> None:
        paths = (
            "\\\\server\\share",
            "\\\\server\\share\\",
            "\\\\server\\share\\papers\\draft.tex",
            "\\\\server\\share\\draft.tex",
            "\\\\10.0.0.2\\C$\\Users\\alice\\draft.tex",
        )

        for path in paths:
            with self.subTest(path=path):
                text = f"Open {path} for a private draft."
                self.assertEqual(scrub_text(text), "Open for a private draft.")
                self.assertTrue(has_locator(text))
                self.assertFalse(has_locator(scrub_text(text)))

        spaced = ("\\\\server\\My Share", "\\\\server\\My Share\\")
        for path in spaced:
            with self.subTest(path=path):
                self.assertEqual(scrub_text(path), "")
                self.assertTrue(has_locator(path))

        deep = "\\\\server\\My Share\\draft.tex"
        self.assertEqual(scrub_text(deep), "")
        self.assertTrue(has_locator(deep))

    def test_author_contact(self) -> None:
        self.assertEqual(
            scrub_author("Ada Researcher <ada@university.edu>"), "Ada Researcher"
        )
        self.assertEqual(scrub_author("ccarilli@nrao. edu"), "")
        self.assertEqual(scrub_author("Ada <ada@example. EDU>"), "Ada")
        self.assertEqual(scrub_author("owner@localhost"), "")
        self.assertEqual(scrub_author("owner@localhostX"), "owner@localhostX")
        self.assertEqual(scrub_contact("Mail ada@example.edu."), "")
        self.assertEqual(scrub_contact("Mail owner@localhost."), "")
        self.assertEqual(scrub_author("ada@example.edu."), "")
        self.assertEqual(scrub_contact("Contact ada@example.edu."), "")
        self.assertEqual(scrub_contact("Correspondence: ada@example. edu."), "")
        self.assertEqual(scrub_contact("Contact ada@example. EDU"), "")
        self.assertEqual(scrub_contact("Email: ada@example. COM"), "")
        self.assertEqual(scrub_contact("Mail ada@example. Org"), "")
        self.assertEqual(
            scrub_contact("Note ada@example. EDU remains"),
            "Note ada@example. EDU remains",
        )
        self.assertEqual(scrub_contact("Contact ada＠example.edu"), "")
        self.assertEqual(scrub_contact("Contact ada@example．edu"), "")
        self.assertEqual(scrub_contact("Contact ada＠example．edu。"), "")
        self.assertEqual(
            scrub_contact("Metric ada@example.edu.123 remains"),
            "Metric ada@example.edu.123 remains",
        )
        self.assertEqual(
            scrub_contact(
                "Under review. Correspondence should be addressed to author@example.edu"
            ),
            "Under review.",
        )

    def test_metric_prose(self) -> None:
        for text in (
            "Recall@10. On held-out data",
            "NDCG@20. These results",
            "Recall@K. On held-out data",
            "Precision@k. The score",
            "Hits@N. We report",
            "Pass@K. This improves robustness",
            "Recall@k. Results follow",
            "Recall@K. Net performance improves",
            "Pass@N. Org results follow",
            "Metric@scale. Com performance",
            "Score@model. Edu results",
        ):
            with self.subTest(text=text):
                self.assertEqual(scrub_contact(text), text)

    def test_mixed_authors(self) -> None:
        paper = {"authors": ["Ada <ada@example.edu>", None]}

        self.assertEqual(scrub_paper(paper)["authors"], ["Ada", None])

    def test_checkpoint_tree(self) -> None:
        value = {
            "abstract": (
                "Email author@example.edu or open "
                "https://www.overleaf.com/project/5e2b14694c5dc600017292e6."
            ),
            "nested": ["Read /Users/alice/private/draft.tex"],
        }

        cleaned = scrub_tree(value)

        self.assertNotIn("example.edu", str(cleaned))
        self.assertNotIn("overleaf.com/project", str(cleaned))
        self.assertNotIn("/Users/", str(cleaned))


if __name__ == "__main__":
    unittest.main()
