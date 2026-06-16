from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from src.advisorkhoj import AdvisorKhojClient, AdvisorKhojError
from src.ppt_generator import build_ranking_deck


st.set_page_config(page_title="Mutual Fund Ranking PPT", layout="wide")

st.title("Mutual Fund Ranking PPT")
st.caption(
    "Enter mutual fund scheme names, verify the AdvisorKhoj matches, "
    "then download a PowerPoint in the RM ranking format."
)

scheme_text = st.text_area(
    "Scheme names",
    height=180,
    placeholder=(
        "Nippon India Large Cap Fund Growth\n"
        "SBI Large Cap Fund Growth\n"
        "Motilal Oswal Midcap Fund Direct Growth"
    ),
    help="Enter one scheme per line. Maximum 21 schemes per presentation.",
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

if st.button("Fetch rankings", type="primary", disabled=not schemes):
    if len(schemes) > 21:
        st.error("The supplied template supports a maximum of 21 schemes.")
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
        progress.empty()

if "ranking_rows" in st.session_state:
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
