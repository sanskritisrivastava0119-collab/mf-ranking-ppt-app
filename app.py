from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from src.advisorkhoj import AdvisorKhojClient, AdvisorKhojError
from src.ppt_generator import MAX_SCHEMES, build_ranking_deck


st.set_page_config(page_title="Mutual Fund Ranking PPT", layout="wide")

st.title("Mutual Fund Ranking PPT")
st.caption(
    "Enter mutual fund scheme names, verify the AdvisorKhoj matches, "
    "then download a PowerPoint in the RM ranking format."
)
st.caption(
    "Tip: names ending with (G) or Growth are treated as Regular plans. "
    "If AdvisorKhoj search misses a scheme, the app tries Moneycontrol to resolve the scheme/category, "
    "then still ranks it against AdvisorKhoj category data."
)

scheme_text = st.text_area(
    "Scheme names",
    height=180,
    placeholder=(
        "Nippon India Large Cap Fund Growth\n"
        "SBI Large Cap Fund Growth\n"
        "Motilal Oswal Midcap Fund Direct Growth"
    ),
    help=f"Enter one scheme per line. Maximum {MAX_SCHEMES} schemes per presentation.",
)

schemes = [line.strip() for line in scheme_text.splitlines() if line.strip()]

plan_type = st.selectbox(
    "Plan type",
    ["Regular", "Direct"],
    help=(
        "AdvisorKhoj shows different ranks for Regular and Direct plans. "
        "Choose the same plan type you are checking on the website."
    ),
)

current_input_signature = (tuple(schemes), plan_type)
if st.session_state.get("ranking_input_signature") != current_input_signature:
    st.session_state.pop("ranking_rows", None)
    st.session_state.pop("ranking_fetch_summary", None)

if st.button("Fetch rankings", type="primary", disabled=not schemes):
    if len(schemes) > MAX_SCHEMES:
        st.error(f"The supplied template supports a maximum of {MAX_SCHEMES} schemes.")
    else:
        client = AdvisorKhojClient()
        rows = []
        progress = st.progress(0, text="Connecting to AdvisorKhoj...")

        for index, scheme in enumerate(schemes):
            try:
                result = client.get_scheme_ranking(scheme, plan_type=plan_type)
                rows.append(result.as_dict())
            except AdvisorKhojError as exc:
                rows.append(
                    {
                        "Requested Scheme": scheme,
                        "Scheme": scheme,
                        "Category": "",
                        "1Y": "-",
                        "3Y": "-",
                        "5Y": "-",
                        "Status": str(exc),
                    }
                )
            progress.progress(
                (index + 1) / len(schemes),
                text=f"Processed {index + 1} of {len(schemes)} schemes",
            )

        st.session_state["ranking_rows"] = rows
        st.session_state["ranking_input_signature"] = current_input_signature
        failed_count = sum(1 for row in rows if row["Status"] != "OK")
        st.session_state["ranking_fetch_summary"] = (
            f"Fetched {len(rows) - failed_count} of {len(rows)} ranking row(s)."
        )
        progress.empty()

if "ranking_rows" in st.session_state:
    if st.session_state.get("ranking_fetch_summary"):
        st.success(st.session_state["ranking_fetch_summary"])

    st.subheader("Review before export")
    st.info(
        "Edit any matched scheme, category, or ranking below. "
        "This review step protects against similarly named Regular/Direct plans."
    )

    editor_df = pd.DataFrame(st.session_state["ranking_rows"])
    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        disabled=["Requested Scheme"],
        column_order=[
            "Requested Scheme",
            "Scheme",
            "Category",
            "1Y",
            "3Y",
            "5Y",
            "Status",
        ],
    )

    valid_rows = edited_df[edited_df["Status"].fillna("").eq("OK")].to_dict("records")
    failed_count = len(edited_df) - len(valid_rows)

    if failed_count:
        st.warning(
            f"{failed_count} row(s) are unresolved. Correct the values and set Status to OK "
            "to include them in the presentation."
        )

    if valid_rows:
        ppt_bytes = build_ranking_deck(valid_rows)
        st.download_button(
            "Download ranking PowerPoint",
            data=io.BytesIO(ppt_bytes),
            file_name="mutual-fund-rankings.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
        )

st.divider()
st.caption(
    "Source: AdvisorKhoj public mutual fund research pages. "
    "Rankings are read from AdvisorKhoj's published trailing-return rank table. "
    "Verify data before investment or client communication."
)
