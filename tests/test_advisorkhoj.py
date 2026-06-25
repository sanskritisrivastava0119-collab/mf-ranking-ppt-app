from src.advisorkhoj import (
    AdvisorKhojClient,
    _advisor_category,
    _advisor_search_query,
    _category_hint_from_query,
    _effective_plan_type,
    _scheme_match_score,
)


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


def test_parse_index_fund_table_computes_rank_within_subcategory():
    html = """
    <table id="tbl_scheme_returns1"><tbody>
      <tr><td>UTI Nifty 500 Value 50 Index Fund Reg Gr</td><td>Equity: Strategy</td>
        <td>10-05-2023</td><td>747.53</td><td>1.14</td><td>20.66</td><td>29.49</td><td>-</td><td>-</td><td>30.54</td></tr>
      <tr><td>ABC Nifty 50 Index Fund Reg Gr</td><td>Equity: Large Cap</td>
        <td>01-01-2010</td><td>100</td><td>0.5</td><td>-2.0</td><td>10.0</td><td>9.0</td><td>-</td><td>10.0</td></tr>
      <tr><td>UTI Nifty 50 Index Fund Reg Gr</td><td>Equity: Large Cap</td>
        <td>06-03-2000</td><td>27812</td><td>0.35</td><td>-3.1</td><td>9.58</td><td>9.75</td><td>12.33</td><td>11.28</td></tr>
      <tr><td>XYZ Nifty 50 Index Fund Reg Gr</td><td>Equity: Large Cap</td>
        <td>01-01-2010</td><td>100</td><td>0.5</td><td>-4.0</td><td>8.0</td><td>8.0</td><td>-</td><td>10.0</td></tr>
    </tbody></table>
    """

    result = AdvisorKhojClient.parse_trailing_return_ranks(
        "UTI Nifty 50 Index Fund", html
    )

    assert result.scheme == "UTI Nifty 50 Index Fund Reg Gr"
    assert (result.rank_1y, result.rank_3y, result.rank_5y) == (
        "2/3",
        "2/3",
        "1/3",
    )


def test_match_score_prefers_amc_token_over_generic_category_words():
    query = "Axis Flexi Cap Fund - Regular Plan - Growth"

    assert _scheme_match_score(query, "Axis Flexi Cap Reg Gr") > _scheme_match_score(
        query, "ITI Flexi Cap Fund Reg Gr"
    )


def test_match_score_prefers_nifty_50_over_next_50_variant():
    query = "ICICI Prudential Nifty 50 Index Fund"

    assert _scheme_match_score(
        query, "ICICI Pru Nifty 50 Index Fund Cumulative"
    ) > _scheme_match_score(query, "ICICI Pru Nifty Next 50 Index Gr")


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


def test_growth_marker_forces_regular_plan_type():
    assert _effective_plan_type("Axis Midcap Fund (G)", "Direct") == "Regular"
    assert _effective_plan_type("Axis Midcap Fund Growth", "Direct") == "Regular"


def test_growth_marker_is_removed_before_advisorkhoj_search():
    assert _advisor_search_query("AXIS Midcap Fund (G)") == "AXIS Midcap Fund"
    assert _advisor_search_query("HDFC Small Cap Fund Growth") == "HDFC Small Cap Fund"
    assert (
        _advisor_search_query("Kotak Emerging Equity Fund (G) - Mid Cap")
        == "Kotak Emerging Equity Fund"
    )


def test_category_hint_after_dash_is_used_for_fallback():
    assert (
        _category_hint_from_query("Kotak Emerging Equity Fund (G) - Mid Cap")
        == "Equity: Mid Cap"
    )


def test_moneycontrol_category_is_converted_for_advisorkhoj():
    assert _advisor_category("Mid-Cap") == "Equity: Mid Cap"
    assert _advisor_category("Small-Cap") == "Equity: Small Cap"
    assert _advisor_category("Flexi Cap") == "Equity: Flexi Cap"
    assert _advisor_category("Aggressive Hybrid") == "Hybrid: Aggressive"


def test_direct_marker_overrides_growth_marker():
    assert (
        _effective_plan_type("Axis Midcap Fund Direct Plan Growth", "Regular")
        == "Direct"
    )


def test_match_score_understands_common_abbreviations():
    query = "ABSL Flexi Cap Fund (G)"

    assert _scheme_match_score(
        query, "Aditya Birla Sun Life Flexi Cap Fund Growth Regular Plan"
    ) > _scheme_match_score(query, "Axis Flexi Cap Fund Growth Regular Plan")
