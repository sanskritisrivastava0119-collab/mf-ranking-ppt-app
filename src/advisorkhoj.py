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


def _normalise(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"\b(reg|regular|direct|dir|plan|growth|gr|option)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _tokens(value: str) -> list[str]:
    stop_words = {"fund", "mf", "mutual", "cap", "equity", "scheme"}
    return [token for token in _normalise(value).split() if token not in stop_words]


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
    return score


def _scheme_slug(name: str) -> str:
    # Mirrors the readable scheme URLs used by AdvisorKhoj.
    value = name.strip().replace("&", "and")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value)
    return value.strip("-")


def _number(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
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
                "Referer": f"{BASE_URL}/mutual-funds-research/mutual-fund-information",
            }
        )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(
                method, url, timeout=self.timeout, **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise AdvisorKhojError(f"AdvisorKhoj request failed: {exc}") from exc

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
        matched = self.choose_scheme(query, self.search_schemes(query), plan_type)
        url = urljoin(BASE_URL, f"/mutual-funds-research/{quote(_scheme_slug(matched))}")
        response = self._request("GET", url)
        page_result = self.parse_scheme_page(query, matched, response.url, response.text)
        raw_category = self.extract_category(response.text)
        plan_option = plan_type or ("Direct" if "direct" in matched.lower() else "Regular")
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
            page_result.scheme, ranking_response.text
        )
        return SchemeRanking(
            requested_scheme=page_result.requested_scheme,
            scheme=published.scheme,
            category=page_result.category,
            rank_1y=published.rank_1y,
            rank_3y=published.rank_3y,
            rank_5y=published.rank_5y,
            source_url=ranking_response.url,
        )

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
        table = soup.select_one("#tbl_scheme_returns")
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

        return PublishedRanks(
            scheme=target[0].replace(" | Invest Online", "").strip(),
            rank_1y=target[5] or "-",
            rank_3y=target[7] or "-",
            rank_5y=target[9] or "-",
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
