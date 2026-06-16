<<<<<<< HEAD
# Mutual Fund Ranking PPT

A Streamlit app that accepts mutual fund scheme names, reads public data from
AdvisorKhoj, calculates each scheme's rank within its category for 1Y, 3Y, and
5Y returns, and produces a PowerPoint using the supplied RM template.

## How ranking is calculated

For each selected scheme, the app reads AdvisorKhoj's published trailing-return
rank table for the selected category and plan type, then copies the visible rank
cells for 1Y, 3Y, and 5Y. Example: `9/38`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Deploy with GitHub and Streamlit Community Cloud

1. Create a GitHub repository and upload this folder.
2. Sign in to Streamlit Community Cloud.
3. Choose **Create app** and select the repository.
4. Set the main file path to `app.py`.
5. Deploy.

No API key is currently required.

## Operational notes

- The template supports up to 21 schemes: seven rows on each of three slides.
- Always choose the same Regular/Direct plan type you are checking on
  AdvisorKhoj before export.
- AdvisorKhoj can change its HTML or restrict automated access. The extraction
  logic is isolated in `src/advisorkhoj.py` so it can be updated independently.
- AdvisorKhoj states that distributors wanting to display its research tools
  may contact them for APIs. For a production rollout, obtain permission or an
  official API arrangement.
- The output is research support, not investment advice. Verify all figures
  before sending the deck to a client or RM.
=======
# mf-ranking-ppt-app
>>>>>>> 80e2123873fd68a9fab1cff7a7c968d316936562
