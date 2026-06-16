from io import BytesIO

from pptx import Presentation

from src.ppt_generator import build_ranking_deck


def test_build_deck_removes_unused_slides():
    data = [
        {
            "Scheme": "Example Fund",
            "Category": "Flexi Cap Fund",
            "1Y": "1/10",
            "3Y": "2/9",
            "5Y": "3/8",
        }
    ]

    result = build_ranking_deck(data)
    presentation = Presentation(BytesIO(result))

    assert len(presentation.slides) == 1
    tables = [shape.table for shape in presentation.slides[0].shapes if shape.has_table]
    assert "Example Fund" in tables[0].cell(2, 0).text
