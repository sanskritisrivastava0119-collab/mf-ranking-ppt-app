from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.advisorkhoj.com"
AUTOCOMPLETE_URL = (
    f"{BASE_URL}/mutual-funds-research/autoSuggestAllMfSchemesInSchemeDetailsPage"
)
TRAILING_RETURNS_URL = f"{BASE_URL}/mutual-funds-research/top-performing-mutual-funds"
MONEYCONTROL_AUTOSUGGEST_URL = (
    "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php"
)


class AdvisorKhojError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishedRanks:
    scheme: str
    rank_1y: str
    rank_3y: str
    rank_5y: str


@dataclass(frozen=True)
class SchemeRanking:
    requested_scheme: str
    scheme: str
    category: str
    rank_1y: str
    rank_3y: str
    rank_5y: str
    source_url: str

    def as_dict(self) -> dict[str, str]:
        return {
            "Requested Scheme": self.requested_scheme,
            "Scheme": self.scheme,
            "Category": self.category,
            "1Y": self.rank_1y,
            "3Y": self.rank_3y,
            "5Y": self.rank_5y,
            "Status": "OK",
            "Source URL": self.source_url,
        }


@dataclass(frozen=True)
class MoneycontrolScheme:
    name: str
    url: str
    category: str | None = None


def _expand_abbreviations(value: str) -> str:
    replacements = {
        r"\babsl\b": "aditya birla sun life",
        r"\baditya birla sl\b": "aditya birla sun life",
        r"\baxis\b": "axis",
        r"\bboi\b": "bank of india",
        r"\bdsp\b": "dsp",
        r"\bhdfc\b": "hdfc",
        r"\bhsbc\b": "hsbc",
        r"\bicici pru\b": "icici pru",
        r"\bicici prudential\b": "icici pru",
        r"\blicmf\b": "lic mf",
        r"\bmo\b": "motilal oswal",
        r"\bmotilal oswal\b": "motilal oswal",
        r"\bnippon\b": "nippon india",
        r"\bppfas\b": "parag parikh",
        r"\bppfcb\b": "parag parikh",
        r"\bsbi\b": "sbi",
        r"\buti\b": "uti",
    }
    result = value.lower()
    for pattern, replacement in replacements.items():
        result = re.sub(pattern, replacement, result)
    return result


def _effective_plan_type(query: str, selected_plan_type: str | None = None) -> str:
    lowered = query.lower()
    if re.search(r"\bdirect\b|\bdir\b", lowered):
        return "Direct"
    if re.search(r"\(g\)|\bgrowth\b|\bgr\b", lowered):
        return "Regular"
    if selected_plan_type in {"Regular", "Direct"}:
        return selected_plan_type
    return "Regular"


def _advisor_search_query(query: str) -> str:
    query = re.split(r"\s+(?:-|\u2013|\u2014)\s+", query, maxsplit=1)[0]
    value = re.sub(r"\(g\)", " ", query, flags=re.IGNORECASE)
    value = re.sub(r"\b(growth|regular|reg|direct|dir|plan|option|gr)\b", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip() or query


def _advisor_category(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.replace("-", " ")).strip()
    lowered = cleaned.lower()
    if lowered.startswith(("equity:", "debt:", "hybrid:")):
        prefix, category = cleaned.split(":", 1)
        category = re.sub(r"\s+", " ", category.replace("-", " ")).strip()
        return f"{prefix.title()}: {category}"

    category_map = {
        "aggressive hybrid": "Hybrid: Aggressive",
        "hybrid aggressive": "Hybrid: Aggressive",
        "aggressive": "Hybrid: Aggressive",
        "balanced advantage": "Hybrid: Dynamic Asset Allocation",
        "dynamic asset allocation": "Hybrid: Dynamic Asset Allocation",
        "equity savings": "Hybrid: Equity Savings",
        "conservative hybrid": "Hybrid: Conservative",
        "small cap": "Equity: Small Cap",
        "smallcap": "Equity: Small Cap",
        "mid cap": "Equity: Mid Cap",
        "midcap": "Equity: Mid Cap",
        "large cap": "Equity: Large Cap",
        "largecap": "Equity: Large Cap",
        "large and mid cap": "Equity: Large and Mid Cap",
        "flexi cap": "Equity: Flexi Cap",
        "flexicap": "Equity: Flexi Cap",
        "multi cap": "Equity: Multi Cap",
        "multicap": "Equity: Multi Cap",
        "focused": "Equity: Focused",
        "elss": "Equity: ELSS",
        "value": "Equity: Value",
        "contra": "Equity: Contra",
        "index fund": "Index Fund",
        "index funds": "Index Fund",
        "index": "Index Fund",
    }
    for key, category in category_map.items():
        if key in lowered:
            return category
    return cleaned


def _display_category(value: str) -> str:
    return re.sub(r"^(Equity|Debt|Hybrid):\s*", "", value).replace("-", " ")


def _normalise(value: str) -> str:
    value = _expand_abbreviations(value).replace("&", " and ")
    value = value.replace("prudential", "pru")
    value = re.sub(r"\b(reg|regular|direct|dir|plan|growth|gr|option)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _tokens(value: str) -> list[str]:
    stop_words = {"fund", "mf", "mutual", "cap", "equity", "scheme"}
    return [token for token in _normalise(value).split() if token not in stop_words]


def _index_number_tokens(value: str) -> set[str]:
    return set(re.findall(r"\b(?:50|100|150|200|250|500|1000)\b", value.lower()))


def _index_variant_tokens(value: str) -> set[str]:
    tokens = set()
    value = value.lower()
    if "next" in value:
        tokens.add("next")
    if "equal weight" in value:
        tokens.add("equal-weight")
    if "value" in value:
        tokens.add("value")
    if "shariah" in value:
        tokens.add("shariah")
    return tokens


def _scheme_match_score(query: str, candidate: str) -> float:
    query_norm = _normalise(query)
    candidate_norm = _normalise(candidate)
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    score = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    if query_tokens and candidate_tokens and query_tokens[0] == candidate_tokens[0]:
        score += 0.5
    if query_tokens and candidate_tokens:
        overlap = len(set(query_tokens) & set(candidate_tokens)) / len(set(query_tokens))
        score += overlap * 0.25
    query_numbers = _index_number_tokens(query)
    candidate_numbers = _index_number_tokens(candidate)
    if query_numbers or candidate_numbers:
        if query_numbers == candidate_numbers:
            score += 0.35
        elif query_numbers & candidate_numbers:
            score += 0.1
        else:
            score -= 0.75
    query_variants = _index_variant_tokens(query)
    candidate_variants = _index_variant_tokens(candidate)
    if query_variants != candidate_variants:
        score -= 0.45 * len(query_variants ^ candidate_variants)
    return score


def _scheme_slug(name: str) -> str:
    # Mirrors the readable scheme URLs used by AdvisorKhoj.
    value = name.strip().replace("&", "and")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value)
    return value.strip("-")


def _infer_category_from_name(name: str) -> str | None:
    lowered = name.lower()
    if "index" in lowered or "nifty" in lowered or "sensex" in lowered:
        return "Index Fund"
    if "small cap" in lowered:
        return "Equity: Small Cap"
    if "mid cap" in lowered:
        return "Equity: Mid Cap"
    if "large and mid" in lowered:
        return "Equity: Large and Mid Cap"
    if "large cap" in lowered:
        return "Equity: Large Cap"
    if "flexi cap" in lowered or "flexicap" in lowered:
        return "Equity: Flexi Cap"
    if "focused" in lowered:
        return "Equity: Focused"
    if "elss" in lowered or "tax saver" in lowered:
        return "Equity: ELSS"
    if "value" in lowered:
        return "Equity: Value"
    if "multi cap" in lowered or "multicap" in lowered:
        return "Equity: Multi Cap"
    if "aggressive hybrid" in lowered or "equity hybrid" in lowered:
        return "Hybrid: Aggressive"
    if "balanced advantage" in lowered or "dynamic asset allocation" in lowered:
        return "Hybrid: Dynamic Asset Allocation"
    if "equity savings" in lowered:
        return "Hybrid: Equity Savings"
    if "conservative hybrid" in lowered:
        return "Hybrid: Conservative"
    return None


def _category_hint_from_query(query: str) -> str | None:
    parts = re.split(r"\s+(?:-|\u2013|\u2014)\s+", query, maxsplit=1)
    if len(parts) < 2:
        return _infer_category_from_name(query)
    return _advisor_category(parts[1]) or _infer_category_from_name(query)


def _scheme_name_from_query(query: str) -> str:
    return _advisor_search_query(query)


def _number(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


class MoneycontrolClient:
    def __init__(self, session: requests.Session, timeout: int = 30):
        self.session = session
        self.timeout = timeout

    def search_schemes(self, query: str, plan_type: str) -> list[MoneycontrolScheme]:
        try:
            response = self.session.get(
                MONEYCONTROL_AUTOSUGGEST_URL,
                params={"query": query, "type": "2", "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AdvisorKhojError(f"Moneycontrol fallback search failed: {exc}") from exc

        schemes = []
        for item in payload if isinstance(payload, list) else []:
            name = item.get("name") or item.get("pdt_dis_nm")
            url = item.get("link_src")
            if not name or not url:
                continue
            lowered = name.lower()
            if plan_type == "Direct" and "direct" not in lowered:
                continue
            if plan_type == "Regular" and "direct" in lowered:
                continue
            if "idcw" in lowered or "inc dist" in lowered or "payout" in lowered:
                continue
            schemes.append(MoneycontrolScheme(name=name, url=url))
        return schemes

    def resolve_scheme(self, query: str, plan_type: str) -> MoneycontrolScheme:
        choices = self.search_schemes(query, plan_type)
        if not choices:
            raise AdvisorKhojError("Moneycontrol fallback also found no matching scheme.")
        selected = max(choices, key=lambda item: _scheme_match_score(query, item.name))
        category = self.extract_category(selected.url) or _infer_category_from_name(
            selected.name
        )
        return MoneycontrolScheme(
            name=selected.name,
            url=selected.url,
            category=category,
        )

    def extract_category(self, url: str) -> str | None:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        match = re.search(r"in its ([A-Za-z &:-]+?) category", text)
        if match:
            category = match.group(1).strip()
            if category.lower() == "index funds":
                return "Index Fund"
            return category
        return None


class AdvisorKhojClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                ),
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Referer": f"{BASE_URL}/mutual-funds-research/mutual-fund-information",
            }
        )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last_error: requests.RequestException | None = None
        for _ in range(3):
            try:
                response = self.session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc

        stream_kwargs = dict(kwargs)
        stream_kwargs.pop("stream", None)
        try:
            response = self.session.request(
                method, url, timeout=self.timeout, stream=True, **stream_kwargs
            )
            response.raise_for_status()
            chunks = []
            try:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        chunks.append(chunk)
            except requests.RequestException:
                pass
            if chunks:
                response._content = b"".join(chunks)
                response._content_consumed = True
                return response
        except requests.RequestException as exc:
            last_error = exc
        raise AdvisorKhojError(f"AdvisorKhoj request failed: {last_error}") from last_error

    def search_schemes(self, query: str) -> list[str]:
        response = self._request("POST", AUTOCOMPLETE_URL, data={"query": query})
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdvisorKhojError("AdvisorKhoj returned an invalid search response.") from exc

        suggestions: list[str] = []
        for item in payload if isinstance(payload, list) else []:
            if isinstance(item, str):
                suggestions.append(item)
            elif isinstance(item, dict):
                value = item.get("name") or item.get("value") or item.get("label")
                if value:
                    suggestions.append(str(value))
        return suggestions

    def choose_scheme(
        self, query: str, suggestions: Iterable[str], plan_type: str | None = None
    ) -> str:
        choices = list(suggestions)
        if not choices:
            raise AdvisorKhojError("No matching scheme was found.")
        wanted = _normalise(query)

        if plan_type in {"Regular", "Direct"}:
            plan_word = "direct" if plan_type == "Direct" else "direct"
            if plan_type == "Direct":
                plan_choices = [item for item in choices if plan_word in item.lower()]
            else:
                plan_choices = [item for item in choices if plan_word not in item.lower()]
            if plan_choices:
                choices = plan_choices

        return max(
            choices,
            key=lambda item: _scheme_match_score(wanted, item),
        )

    def get_scheme_ranking(
        self, query: str, plan_type: str | None = None
    ) -> SchemeRanking:
        plan_option = _effective_plan_type(query, plan_type)
        search_query = _advisor_search_query(query)
        try:
            matched = self.choose_scheme(
                query, self.search_schemes(search_query), plan_option
            )
            url = urljoin(BASE_URL, f"/mutual-funds-research/{quote(_scheme_slug(matched))}")
            response = self._request("GET", url)
            page_result = self.parse_scheme_page(query, matched, response.url, response.text)
            raw_category = _advisor_category(self.extract_category(response.text))
            scheme_for_ranking = page_result.scheme
            display_category = page_result.category
        except AdvisorKhojError:
            raw_category = _category_hint_from_query(query)
            if raw_category:
                scheme_for_ranking = _scheme_name_from_query(query)
                display_category = _display_category(raw_category)
            else:
                fallback = MoneycontrolClient(self.session, self.timeout).resolve_scheme(
                    query, plan_option
                )
                raw_category = _advisor_category(fallback.category)
                if not raw_category:
                    raise AdvisorKhojError(
                        "AdvisorKhoj could not resolve this scheme, and Moneycontrol did not provide a category."
                    )
                scheme_for_ranking = fallback.name
                display_category = _display_category(raw_category)
        ranking_response = self._request(
            "GET",
            TRAILING_RETURNS_URL,
            params={
                "category": raw_category,
                "period": "1y",
                "type": "Open Ended",
                "mode": "Growth",
                "option": plan_option,
            },
        )
        published = self.parse_trailing_return_ranks(
            scheme_for_ranking, ranking_response.text
        )
        return SchemeRanking(
            requested_scheme=query,
            scheme=published.scheme,
            category=display_category,
            rank_1y=published.rank_1y,
            rank_3y=published.rank_3y,
            rank_5y=published.rank_5y,
            source_url=ranking_response.url,
        )

    @staticmethod
    def _ranking_from_returns(
        target: list[str], candidates: list[list[str]], return_index: int
    ) -> str:
        values = [
            (cells, _number(cells[return_index]))
            for cells in candidates
            if len(cells) > return_index and _number(cells[return_index]) is not None
        ]
        target_value = _number(target[return_index]) if len(target) > return_index else None
        if target_value is None:
            return "-"
        ordered = sorted(values, key=lambda item: item[1], reverse=True)
        target_name = target[0]
        for position, (cells, _) in enumerate(ordered, start=1):
            if cells[0] == target_name:
                return f"{position}/{len(ordered)}"
        return "-"

    @staticmethod
    def extract_category(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("table tr"):
            text = row.get_text(" ", strip=True)
            if text.lower().startswith("category:"):
                return text.split(":", 1)[1].strip()
        raise AdvisorKhojError("Could not read the scheme category.")

    @staticmethod
    def parse_trailing_return_ranks(
        scheme_name: str, html: str
    ) -> PublishedRanks:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("#tbl_scheme_returns") or soup.select_one(
            "#tbl_scheme_returns1"
        )
        if table is None:
            raise AdvisorKhojError("Could not find the category ranking table.")

        candidates = []
        for row in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if len(cells) >= 10 and cells[0] not in {"Category Average"}:
                candidates.append(cells)
        if not candidates:
            raise AdvisorKhojError("The category ranking table was empty.")

        target = max(
            candidates,
            key=lambda cells: _scheme_match_score(scheme_name, cells[0]),
        )
        similarity = _scheme_match_score(scheme_name, target[0])
        if similarity < 0.55:
            raise AdvisorKhojError("The selected scheme was not found in its category table.")

        # Standard AdvisorKhoj category tables publish explicit rank cells.
        if re.match(r"^\d+/\d+$", target[5]):
            return PublishedRanks(
                scheme=target[0].replace(" | Invest Online", "").strip(),
                rank_1y=target[5] or "-",
                rank_3y=target[7] or "-",
                rank_5y=target[9] or "-",
            )

        # Index Fund / ETF tables publish returns but not rank cells. Rank
        # inside the visible subcategory so Nifty 50 is not compared with
        # unrelated international, sector, or Nifty 500 index funds.
        peer_group = [
            cells for cells in candidates if len(cells) > 1 and cells[1] == target[1]
        ]
        if not peer_group:
            peer_group = candidates
        return PublishedRanks(
            scheme=target[0].replace(" | Invest Online", "").strip(),
            rank_1y=AdvisorKhojClient._ranking_from_returns(target, peer_group, 5),
            rank_3y=AdvisorKhojClient._ranking_from_returns(target, peer_group, 6),
            rank_5y=AdvisorKhojClient._ranking_from_returns(target, peer_group, 7),
        )

    @staticmethod
    def calculate_peer_ranks(
        scheme_name: str, peer_data: list[dict]
    ) -> tuple[str, str, str]:
        if not isinstance(peer_data, list) or not peer_data:
            raise AdvisorKhojError("AdvisorKhoj returned no peer comparison data.")

        target = max(
            peer_data,
            key=lambda item: _scheme_match_score(
                scheme_name, str(item.get("scheme_amfi", ""))
            ),
        )
        fields = ("returns_abs_1year", "returns_cmp_3year", "returns_cmp_5year")
        ranks = []
        for field in fields:
            values = [
                (str(item.get("scheme_amfi", "")), _number(str(item.get(field, ""))))
                for item in peer_data
            ]
            values = [(name, value) for name, value in values if value is not None]
            target_value = _number(str(target.get(field, "")))
            if target_value is None:
                ranks.append("-")
                continue
            ordered = sorted(values, key=lambda item: item[1], reverse=True)
            target_name = str(target.get("scheme_amfi", ""))
            position = next(
                i for i, (name, _) in enumerate(ordered, start=1) if name == target_name
            )
            ranks.append(f"{position}/{len(ordered)}")
        return ranks[0], ranks[1], ranks[2]

    @staticmethod
    def parse_scheme_page(
        requested: str, matched: str, source_url: str, html: str
    ) -> SchemeRanking:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find("h1")
        canonical_name = heading.get_text(" ", strip=True) if heading else matched

        category = AdvisorKhojClient.extract_category(html)

        peer_table = None
        for table in soup.find_all("table"):
            headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
            header_text = " | ".join(headers).lower()
            if "scheme name" in header_text and "1 year" in header_text and "5 year" in header_text:
                peer_table = table
                break
        if peer_table is None:
            raise AdvisorKhojError("Could not find the peer comparison table.")

        headers = [th.get_text(" ", strip=True) for th in peer_table.find_all("th")]
        indexes = {}
        for period in ("1 year", "3 year", "5 year"):
            indexes[period] = next(
                (i for i, header in enumerate(headers) if period in header.lower()),
                None,
            )
        if any(index is None for index in indexes.values()):
            raise AdvisorKhojError("The peer table is missing a ranking period.")

        peer_rows: list[tuple[str, list[str]]] = []
        for tr in peer_table.select("tbody tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if cells:
                peer_rows.append((cells[0], cells))
        if not peer_rows:
            raise AdvisorKhojError("The peer table did not contain any schemes.")

        target = max(
            peer_rows,
            key=lambda row: SequenceMatcher(
                None, _normalise(canonical_name), _normalise(row[0])
            ).ratio(),
        )

        ranks = []
        for period in ("1 year", "3 year", "5 year"):
            column = indexes[period]
            values = [
                (name, _number(cells[column]))
                for name, cells in peer_rows
                if len(cells) > column and _number(cells[column]) is not None
            ]
            target_value = _number(target[1][column]) if len(target[1]) > column else None
            if target_value is None:
                ranks.append("-")
                continue
            ordered = sorted(values, key=lambda item: item[1], reverse=True)
            position = next(
                i for i, (name, _) in enumerate(ordered, start=1) if name == target[0]
            )
            ranks.append(f"{position}/{len(ordered)}")

        clean_category = re.sub(r"^(Equity|Debt|Hybrid):\s*", "", category)
        return SchemeRanking(
            requested_scheme=requested,
            scheme=canonical_name,
            category=clean_category,
            rank_1y=ranks[0],
            rank_3y=ranks[1],
            rank_5y=ranks[2],
            source_url=source_url,
        )
