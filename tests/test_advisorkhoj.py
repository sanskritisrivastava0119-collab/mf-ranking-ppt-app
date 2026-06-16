from src.advisorkhoj import AdvisorKhojClient, _scheme_match_score


HTML = """
<html><body>
<h1>Example Flexi Cap Fund - Regular Plan - Growth</h1>
<table><tr><td>Category: Equity: Flexi Cap</td></tr></table>
<table>
  <thead><tr>
    <th>Scheme Name</th><th>Inception Date</th>
    <th>1 Year Return(%)</th><th>2 Year Return(%)</th>
    <th>3 Year Return(%)</th><th>5 Year Return(%)</th>
  </tr></thead>
  <tbody>
    <tr><td>Example Flexi Cap Fund - Regular Plan - Growth</td><td>01-01-2020</td>
      <td>12</td><td>11</td><td>10</td><td>9</td></tr>
    <tr><td>Peer A</td><td>01-01-2010</td>
      <td>14</td><td>12</td><td>8</td><td>10</td></tr>
    <tr><td>Peer B</td><td>01-01-2010</td>
      <td>8</td><td>9</td><td>12</td><td>7</td></tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_scheme_page_calculates_rank():
    result = AdvisorKhojClient.parse_scheme_page(
        "Example Fund",
        "Example Flexi Cap Fund - Regular Plan - Growth",
        "https://example.test/fund",
        HTML,
    )

    assert result.category == "Flexi Cap"
    assert result.rank_1y == "2/3"
    assert result.rank_3y == "2/3"
    assert result.rank_5y == "2/3"


def test_calculate_peer_ranks_uses_full_peer_payload():
    peers = [
        {
            "scheme_amfi": "Example Fund",
            "returns_abs_1year": 12,
            "returns_cmp_3year": 10,
            "returns_cmp_5year": 9,
        },
        {
            "scheme_amfi": "Peer A",
            "returns_abs_1year": 14,
            "returns_cmp_3year": 8,
            "returns_cmp_5year": 10,
        },
        {
            "scheme_amfi": "Peer B",
            "returns_abs_1year": 8,
            "returns_cmp_3year": 12,
            "returns_cmp_5year": 7,
        },
    ]

    assert AdvisorKhojClient.calculate_peer_ranks("Example Fund", peers) == (
        "2/3",
        "2/3",
        "2/3",
    )


def test_parse_trailing_return_ranks_reads_published_ranks():
    html = """
    <table id="tbl_scheme_returns"><tbody>
      <tr>
        <td>Example Fund Reg Gr</td><td>01-01-2020</td><td>100</td><td>1.5</td>
        <td>12.0</td><td>2/40</td><td>10.0</td><td>3/34</td>
        <td>9.0</td><td>4/24</td><td>-</td><td>-</td><td>11.0</td>
      </tr>
    </tbody></table>
    """

    result = AdvisorKhojClient.parse_trailing_return_ranks(
        "Example Fund Regular Growth", html
    )

    assert result.scheme == "Example Fund Reg Gr"
    assert (result.rank_1y, result.rank_3y, result.rank_5y) == (
        "2/40",
        "3/34",
        "4/24",
    )


def test_match_score_prefers_amc_token_over_generic_category_words():
    query = "Axis Flexi Cap Fund - Regular Plan - Growth"

    assert _scheme_match_score(query, "Axis Flexi Cap Reg Gr") > _scheme_match_score(
        query, "ITI Flexi Cap Fund Reg Gr"
    )


def test_choose_scheme_respects_regular_plan_type():
    client = AdvisorKhojClient()
    choices = [
        "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        "Parag Parikh Flexi Cap Fund - Growth",
    ]

    assert client.choose_scheme(
        "Parag Parikh Flexi Cap Fund Direct Plan Growth",
        choices,
        plan_type="Regular",
    ) == "Parag Parikh Flexi Cap Fund - Growth"


def test_choose_scheme_respects_direct_plan_type():
    client = AdvisorKhojClient()
    choices = [
        "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        "Parag Parikh Flexi Cap Fund - Growth",
    ]

    assert client.choose_scheme(
        "Parag Parikh Flexi Cap Fund Growth",
        choices,
        plan_type="Direct",
    ) == "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"
