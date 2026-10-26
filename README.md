# BioSage

**An AI scientific research assistant that discovers papers, explains findings, and interprets research tables with traceable evidence.**

BioSage is being built for the Nebius Global AI Hackathon. Its goal is to help students and early-career researchers understand scientific literature without losing the link to the original evidence.

## Current MVP

- Search biomedical literature through Europe PMC.
- Display paper titles, authors, journals, abstracts when available, and direct source links.
- Ask for a plain-language explanation grounded in retrieved metadata and abstracts.
- Paste a DOI, PubMed link, or Europe PMC link to retrieve a paper record and ask a question.
- Call a configured model through Nebius Token Factory's OpenAI-compatible API.
- Be explicit when the app has only abstract/metadata access; this version does **not** yet parse full-text tables or figures.

## Run locally

Requires Python 3.10+.

1. Clone this repository and open a terminal in the project folder.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, then set your Nebius API key and an available eligible model:

   ```env
   NEBIUS_API_KEY=your_key_here
   NEBIUS_MODEL=your_available_model_id
   NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
   ```

5. Load the environment variables in your terminal/session, then run:

   ```bash
   uvicorn app:app --reload
   ```

6. Open http://127.0.0.1:8000. Check http://127.0.0.1:8000/api/health for API status.

Do not commit API keys or place them in browser-side JavaScript. Model availability and IDs can change; use the current Nebius Token Factory console/docs to choose a model that satisfies the hackathon's NVIDIA open-source-model requirement.

## Current limitations

- Literature search currently focuses on biomedical sources indexed by Europe PMC.
- Paper-link resolution supports DOI, PubMed, Europe PMC, and PubMed Central identifiers.
- A link resolving to metadata/abstract does not imply full-text access.
- Full-text PDF parsing, exact table/figure extraction, table explanations, and robust citation-level verification are planned features, not yet implemented.
- AI outputs can be wrong. Check the original sources, especially before using results in health-related decisions.

## Planned roadmap

1. Full-text access where legally and technically available.
2. PDF upload and paper question-answering.
3. Table/figure extraction with original values preserved.
4. Claim-to-source evidence mapping and uncertainty labels.
5. Evaluation tests using known papers and questions.
6. Deployment and a short demonstration video.

## License

MIT. See `LICENSE`.
