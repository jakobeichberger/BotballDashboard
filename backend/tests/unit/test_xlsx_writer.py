"""The standard-library XLSX writer behind the results export."""

import io
import zipfile

from modules.exports.xlsx import Sheet, _column, build_xlsx
from tests.integration.test_results_export_ecer_2026 import read_xlsx


def test_columns_beyond_z():
    assert [_column(i) for i in (0, 25, 26, 27, 701, 702)] == ["A", "Z", "AA", "AB", "ZZ", "AAA"]


def test_values_escaping_and_sheet_names():
    content = build_xlsx(
        [
            Sheet("Botball & Open", [["Team", "Score"], ["<b>Ü&</b>\x01", 1.25], [None, 3]], {0}),
            Sheet("Botball & Open", [[True]]),
            Sheet("a/b:c*d?[e]" + "x" * 40, []),
        ]
    )
    archive = zipfile.ZipFile(io.BytesIO(content))
    assert "xl/styles.xml" in archive.namelist()
    sheets = read_xlsx(content)
    names = list(sheets)
    assert names[:2] == ["Botball & Open", "Botball & Open (2)"]
    assert len(names[2]) <= 31 and not set("/:*?[]") & set(names[2])
    assert sheets["Botball & Open"] == [["Team", "Score"], ["<b>Ü&</b>", 1.25], [None, 3.0]]
    # The header row is bold (style 1).
    sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode()
    assert '<c r="A1" t="inlineStr" s="1">' in sheet_xml
    assert '<c r="A2" t="inlineStr">' in sheet_xml


def test_empty_workbook_still_has_a_sheet():
    assert list(read_xlsx(build_xlsx([]))) == ["Sheet"]
