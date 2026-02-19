from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def summarize_table(object_name: str, transcripts: dict[str, str]) -> str:
    """Summarize voice transcripts into a cohesive table description."""
    parts = []
    label_map = {
        "usage": "What the table is used for",
        "metrics": "Metrics and KPIs derived from this table",
        "stakeholders": "Key stakeholders",
    }
    for key, text in transcripts.items():
        label = label_map.get(key, key)
        parts.append(f"- {label}: {text}")

    transcript_block = "\n".join(parts)

    response = _get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data documentation specialist. Summarize the following "
                    "voice transcripts into a clear, professional description for a "
                    "data catalog entry. The description should be 2-4 sentences, "
                    "written in third person, and suitable for a data dictionary. "
                    "Include the purpose, key metrics, and stakeholders."
                ),
            },
            {
                "role": "user",
                "content": f"Table: {object_name}\n\nTranscripts:\n{transcript_block}",
            },
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def summarize_column(object_name: str, column_name: str, transcript: str) -> str:
    """Summarize a voice transcript into a column description."""
    response = _get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data documentation specialist. Summarize the following "
                    "voice transcript into a concise column description for a data "
                    "catalog. The description should be 1-2 sentences, written in "
                    "third person, and clearly explain what the column represents."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Table: {object_name}\n"
                    f"Column: {column_name}\n\n"
                    f"Transcript: {transcript}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()
