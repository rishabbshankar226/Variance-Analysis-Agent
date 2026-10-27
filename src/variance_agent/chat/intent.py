"""Deterministic intent parser using ordered regex patterns.

Each user message is matched against patterns top-to-bottom.  The first
match wins.  No ML, no fuzzy matching -- every resolution is reproducible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Longest message the intent patterns see. Real commands are a few dozen characters; anything
# past this is pasted text, and long inputs are what make regex matching slow.
MAX_ROUTING_CHARS = 500
# The message as typed may carry padding (blanks, invisible characters) that routing drops, but
# no more than this, so nothing long is ever stored or echoed back.
MAX_RAW_MESSAGE_CHARS = 4 * MAX_ROUTING_CHARS

_ROUTING_FOLDS = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2212": "-",
})


def normalize_for_routing(text: str) -> str:
    """The copy of a message that intent parsing and item matching work on.

    NFKC (full-width letters, NBSP and other odd spaces), curly quotes and dashes folded to
    ASCII, invisible format characters dropped, whitespace collapsed. It is never stored or
    shown back: periods, labels and file names keep the user's exact characters.
    """
    if text.isascii() and text.isprintable() and "  " not in text and text == text.strip():
        return text  # nothing to fold: the common case for account names
    folded = unicodedata.normalize("NFKC", text).translate(_ROUTING_FOLDS)
    visible = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    return " ".join(visible.split())


@dataclass(frozen=True)
class ParsedIntent:
    """Result of intent parsing."""

    intent_id: str
    captures: dict[str, str]


KNOWLEDGE_INTENTS: frozenset[str] = frozenset({
    "concept_consensus", "concept_surprise", "concept_beat_miss", "concept_bps",
    "concept_guidance_range", "concept_standardized_surprise",
    "concept_variance",
    "concept_f_vs_u",
    "concept_fav",
    "concept_unfav",
    "concept_materiality",
    "concept_net_impact",
    "concept_drivers",
    "concept_unclassified",
    "concept_audit",
    "concept_actions",
    "concept_formats",
    "concept_budget_forecast",
    "concept_timing_permanent",
    "concept_operating_leverage",
    "concept_kpis",
    "concept_budgeting_methods",
    "concept_ebitda_margin",
    "concept_bridge",
    "comparison_types",
})

# Ordered list of (compiled_regex, intent_id).
# Evaluated top-to-bottom; first match wins.
_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^review\s+earnings$", re.IGNORECASE), "earnings_review"),
    (re.compile(r"^(?:what\s+is|explain|define)\s+(?:street\s+)?consensus\??$", re.IGNORECASE), "concept_consensus"),
    (re.compile(r"^(?:what\s+is|explain|define)\s+(?:earnings\s+)?surprise\??$", re.IGNORECASE), "concept_surprise"),
    (re.compile(r"^(?:what\s+do\s+beat\s+and\s+miss\s+mean|explain\s+beat\s+and\s+miss)\??$", re.IGNORECASE), "concept_beat_miss"),
    (re.compile(r"^(?:what\s+are|explain|define)\s+(?:basis\s+points|bps)\??$", re.IGNORECASE), "concept_bps"),
    (re.compile(r"^(?:how\s+do\s+guidance\s+ranges\s+work|explain\s+guidance\s+ranges)\??$", re.IGNORECASE), "concept_guidance_range"),
    (re.compile(r"^(?:what\s+is|explain|define)\s+(?:standardized\s+surprise|sue)\??$", re.IGNORECASE), "concept_standardized_surprise"),
    (re.compile(r"^(?:did\s+we\s+beat\s+(?:the\s+)?consensus|(?:vs\.?|versus)\s+(?:the\s+)?street)\??$",
                re.IGNORECASE), "earnings_consensus"),
    (re.compile(r"^margins?\s+in\s+(?:bps|basis\s+points)\??$", re.IGNORECASE), "earnings_margins"),
    (re.compile(r"^where\s+are\s+we\s+(?:vs\.?|versus)\s+(?:the\s+)?guid(?:e|ance)\??$", re.IGNORECASE), "earnings_guidance"),
    (re.compile(
        r"^(?:help|commands|menu|\?|what\s+can\s+you\s+do|can\s+you\s+help(?:\s+me)?|how\s+do\s+i\s+use\s+this|what\s+should\s+i\s+do)\??$",
        re.IGNORECASE,
    ), "help"),

    (re.compile(
        r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|greetings|howdy|sup)\b(?:\s+there|\s+agent|\s+bot)?\s*[!.]*$",
        re.IGNORECASE,
    ), "greeting"),

    (re.compile(
        r"^(?:thanks(?:\s+(?:so\s+much|a\s+lot|very\s+much))?|thank\s+you(?:\s+(?:so\s+much|very\s+much))?|thx|awesome|great(?:\s+job|\s+work)?|perfect|cool|sounds\s+good|got\s+it|understood|appreciate\s+it|much\s+appreciated)\s*[!.]*$",
        re.IGNORECASE,
    ), "gratitude"),

    (re.compile(
        r"^(?:(?:tell\s+me\s+)?(?:who|what)\s+(?:are\s+you|is\s+this(?:\s+agent|\s+bot|\s+tool)?)|who\s+made\s+you)\??$",
        re.IGNORECASE,
    ), "identity"),

    (re.compile(
        r"^(?:(?:give\s+me\s+)?(?:the\s+)?(?:tl;?dr|takeaway|in\s+a\s+nutshell|quick\s+take|headline|readout)"
        r"|what\'?s\s+the\s+(?:short\s+story|tl;?dr|takeaway|headline)"
        r"|how\s+did\s+we\s+(?:do|perform)(?:\s+(?:this|last|the)\s+quarter)?"
        r"|how\s+are\s+we\s+doing"
        r"|how\s+was\s+(?:the|our|this)\s+(?:quarter|period|performance)"
        r"|did\s+we\s+(?:beat|hit|make)\s+(?:the\s+)?(?:plan|budget|target|numbers?)"
        r"|nutshell)\??$",
        re.IGNORECASE,
    ), "tldr"),

    (re.compile(
        r"^(?:are\s+we\s+(?:in\s+the\s+black(?:\s+or\s+(?:in\s+)?the\s+red)?|in\s+the\s+red(?:\s+or\s+(?:in\s+)?the\s+black)?|profitable|making\s+money|losing\s+money)|how\s+is\s+(?:our\s+|the\s+)?(?:profitability|bottom\s+line|operating\s+income)|profitability)\??$",
        re.IGNORECASE,
    ), "profitability"),

    (re.compile(
        r"^(?:new|reset|start\s*over|clear)$", re.IGNORECASE,
    ), "reset"),

    (re.compile(
        r"^(?:export|save|download|write)\s+(?:report|md|markdown)"
        r"(?:\s+(?:to\s+)?(?P<path>.+))?$",
        re.IGNORECASE,
    ), "export_report"),

    (re.compile(
        r"^(?:export|save|download|write)\s+(?:audit|json)"
        r"(?:\s+(?:to\s+)?(?P<path>.+))?$",
        re.IGNORECASE,
    ), "export_audit"),

    (re.compile(
        r"^(?:export|save|download|write)\s+(?:excel|xlsx|workbook|spreadsheet)"
        r"(?:\s+(?:to\s+)?(?P<path>.+))?$",
        re.IGNORECASE,
    ), "export_xlsx"),

    (re.compile(
        r"^(?:export|save|download|write)\s+(?:data|csv|table)"
        r"(?:\s+(?:to\s+)?(?P<path>.+))?$",
        re.IGNORECASE,
    ), "export_csv"),

    (re.compile(
        r"^(?:summary|overview|executive\s+summary|bottom\s+line|kpis?)$",
        re.IGNORECASE,
    ), "summary"),

    (re.compile(
        r"^(?:(?P<count>count|include|keep)\s+(?:the\s+)?hidden\s+rows?"
        r"|(?:leave|keep)\s+(?:the\s+)?hidden\s+rows?\s+out|(?:exclude|skip|drop)\s+(?:the\s+)?hidden\s+rows?)\.?$",
        re.IGNORECASE,
    ), "set_hidden_rows"),

    (re.compile(
        r"^(?:(?:please\s+)?compare\s+to\s+(?:the\s+)?(?P<basis>budget|forecast|prior\s+year|last\s+year|prior\s+period|consensus|estimate|guidance))\??$",
        re.IGNORECASE,
    ), "set_comparison"),

    # ── Financial Knowledge & Concepts ──────────────────────────────
    (re.compile(
        r"^(?:what\s+(?:can\s+i\s+compare\s+(?:against|to)|are\s+the\s+comparison\s+(?:types|bases|options))|comparison\s+types)\??$",
        re.IGNORECASE,
    ), "comparison_types"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:variance\s+analysis|budget\s+(?:vs\.?|versus)\s+actual|bva|what\s+does\s+this\s+(?:agent|tool)\s+do)\??$",
        re.IGNORECASE,
    ), "concept_variance"),

    (re.compile(
        r"^(?:(?:why|explain|what\s+is|difference\s+between)\s+)?"
        r"(?:favou?rable\s+(?:vs\.?|versus|and|or)\s+unfavou?rable|f\s+(?:vs\.?|versus|and|or)\s+u"
        r"|positive\s+(?:cost|expense)?\s*variance\s+unfavou?rable"
        r"|unfavou?rable\s+when\s+positive)\??$",
        re.IGNORECASE,
    ), "concept_f_vs_u"),

    (re.compile(
        r"^(?:what\s+(?:does|is)|explain|define|meaning\s+of)\s+favou?rable(?:\s+variance)?(?:\s+mean)?\??$",
        re.IGNORECASE,
    ), "concept_fav"),

    (re.compile(
        r"^(?:what\s+(?:does|is)|explain|define|meaning\s+of)\s+unfavou?rable(?:\s+variance)?(?:\s+mean)?\??$",
        re.IGNORECASE,
    ), "concept_unfav"),

    (re.compile(
        r"^(?:what\s+is|explain|how\s+does|why\s+both\s+dollar\s+and\s+percent)\s+"
        r"(?:the\s+)?materiality(?:\s+thresholds?|\s+rule|\s+logic)?\??$",
        re.IGNORECASE,
    ), "concept_materiality"),

    (re.compile(
        r"^(?:(?:what\s+is|how\s+is\s+calculated|explain)\s+)?"
        r"(?:the\s+)?net\s+(?:operating\s+)?impact(?:\s+calculated)?\??$",
        re.IGNORECASE,
    ), "concept_net_impact"),

    (re.compile(
        # Bare "drivers" is the data-backed driver summary, so the concept needs a question prefix.
        r"^(?:(?:what\s+(?:is|are)|explain)\s+(?:causal\s+)?(?:driver\s+decomposition|drivers?|price\s+volume(?:\s+mix)?|rate\s+volume)"
        r"|(?:causal\s+)?(?:driver\s+decomposition|price\s+volume(?:\s+mix)?|rate\s+volume))\??$",
        re.IGNORECASE,
    ), "concept_drivers"),

    (re.compile(
        r"^(?:what\s+is|why|explain)\s+(?:an?\s+)?unclassified(?:\s+items?|\s+lines?)?(?:\s+matters?)?\??$",
        re.IGNORECASE,
    ), "concept_unclassified"),

    (re.compile(
        r"^(?:(?:what\s+is|explain|how\s+does)\s+(?:the\s+)?)?(?:audit\s+trail|audit\s+record|provenance|fingerprint)\??$",
        re.IGNORECASE,
    ), "concept_audit"),

    (re.compile(
        r"^(?:(?:how\s+to\s+handle|what\s+actions?\s+to\s+take|playbook\s+for|how\s+to\s+mitigate)\s+"
        r"unfavou?rable(?:\s+variances?)?|(?:action\s+)?playbook)\??$",
        re.IGNORECASE,
    ), "concept_actions"),

    (re.compile(
        r"^(?:what\s+file\s+formats?|what\s+formats?|supported\s+(?:file\s+)?formats?|file\s+formats?|file\s+requirements?|what\s+columns?|schema)\??$",
        re.IGNORECASE,
    ), "concept_formats"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:the\s+)?(?:difference\s+between\s+)?(?:budget\s+(?:vs\.?|versus|and)\s+forecast|forecast\s+(?:vs\.?|versus|and)\s+budget|prior\s+period\s+vs\s+budget)\??$",
        re.IGNORECASE,
    ), "concept_budget_forecast"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:the\s+)?(?:difference\s+between\s+)?(?:timing\s+(?:vs\.?|versus|and)\s+permanent(?:\s+variances?)?|timing\s+variance|permanent\s+variance|run\s*rate\s+vs\s+one\s*off)\??$",
        re.IGNORECASE,
    ), "concept_timing_permanent"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:operating\s+leverage|fixed\s+(?:vs\.?|versus|and)\s+variable(?:\s+costs?)?|flow\s*through|drop\s*through)\??$",
        re.IGNORECASE,
    ), "concept_operating_leverage"),

    (re.compile(
        r"^(?:(?:what\s+(?:is|are)|explain|define)\s+)?(?:financial\s+)?(?:kpis?|metrics\s+explained)\??$",
        re.IGNORECASE,
    ), "concept_kpis"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:zero\s+based\s+budgeting|zbb|incremental\s+budgeting|budgeting\s+methods?)\??$",
        re.IGNORECASE,
    ), "concept_budgeting_methods"),

    (re.compile(
        r"^(?:what\s+is\s+)?(?:the\s+)?(?:ebitda|operating\s+income|gross\s+margin|profit|margin\s+impact|flow\s*through)(?:\s+impact|\s+analysis)?\??$",
        re.IGNORECASE,
    ), "concept_ebitda_margin"),

    (re.compile(
        r"^(?:(?:what\s+is|explain|how\s+does)\s+(?:a\s+)?(?:p&l\s+bridge|variance\s+bridge|waterfall\s+chart|variance\s+waterfall)(?:\s+(?:work|mean|explained))?"
        r"|(?:p&l\s+bridge|variance\s+bridge|waterfall\s+chart|variance\s+waterfall)\s+(?:work|mean|explained))\??$",
        re.IGNORECASE,
    ), "concept_bridge"),

    # ── Advanced Financial Analytics on Data ────────────────────────
    (re.compile(
        r"^(?:show\s+)?(?:the\s+)?(?:p&l\s+)?(?:variance\s+)?(?:waterfall|bridge|walk)(?:\s+(?:chart|table|analysis))?\??$",
        re.IGNORECASE,
    ), "waterfall"),

    (re.compile(
        r"^(?:(?:show\s+|generate\s+|create\s+|write\s+|draft\s+)?(?:executive\s+)?(?:memo|briefing|commentary|cfo\s+memo|management\s+(?:memo|briefing|report|commentary))"
        r"|summarize\s+(?:this\s+)?for\s+(?:the\s+)?(?:board|cfo|ceo|leadership|executives?)"
        r"|what\s+should\s+i\s+tell\s+(?:the\s+)?(?:board|cfo|ceo|leadership))\??$",
        re.IGNORECASE,
    ), "executive_memo"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:causal\s+)?(?:driver\s+models?|driver\s+summary|drivers\s+overview|drivers\s+table)\??$"
        r"|^(?:drivers\s+summary|drivers?)\??$",
        re.IGNORECASE,
    ), "driver_summary"),
    (re.compile(
        r"^(?:(?:what\s+(?:is|are)\s+(?:our\s+)?|show\s+(?:me\s+)?(?:the\s+|our\s+)?)?"
        r"(?:biggest\s+risks?|top\s+concerns?|what\s+should\s+i\s+worry\s+about|what\s+went\s+wrong|worst\s+variances?|biggest\s+(?:cost\s+)?overruns?|key\s+risks?)"
        r"|where\s+are\s+we\s+bleeding(?:\s+money|\s+cash)?|bleeding\s+(?:money|cash)|cash\s+bleed"
        r"|where\s+are\s+we\s+losing\s+money|what\s+hurts\s+the\s+most|where\s+is\s+the\s+leak)\??$",
        re.IGNORECASE,
    ), "biggest_risks"),

    (re.compile(
        r"^(?:(?:what\s+(?:is|are)\s+(?:our\s+)?|show\s+(?:me\s+)?(?:the\s+|our\s+)?)?"
        r"(?:biggest\s+wins?|what\s+went\s+well|what\s+went\s+right|where\s+did\s+we\s+beat(?:\s+budget)?|top\s+(?:positive|favou?rable)\s+variances?|best\s+performers?)"
        r"|where\s+are\s+we\s+winning|where\s+did\s+we\s+outperform)\??$",
        re.IGNORECASE,
    ), "biggest_wins"),

    (re.compile(
        r"^(?:did\s+(?:we|revenue|sales)\s+(?:hit|beat|meet)\s+(?:the\s+)?(?:revenue\s+)?(?:budget|targets?)|revenue\s+(?:status|performance)|how\s+did\s+(?:revenue|sales)\s+(?:do|perform))\??$",
        re.IGNORECASE,
    ), "revenue_status"),

    (re.compile(
        r"^(?:did\s+expenses?\s+(?:stay\s+in|beat|exceed)\s+budget|are\s+expenses?\s+over\s+budget|did\s+we\s+overspend|expense\s+(?:status|performance)|cost\s+control|how\s+did\s+expenses?\s+(?:do|perform))\??$",
        re.IGNORECASE,
    ), "expense_status"),

    (re.compile(
        r"^(?:what\s+percentage\s+of\s+budget\s+was\s+spent|budget\s+utilization|burn\s+rate|spend\s+rate|budget\s+execution)\??$",
        re.IGNORECASE,
    ), "budget_utilization"),

    (re.compile(
        r"^(?:show\s+)?(?:highest|top|biggest)\s+percent(?:age)?(?:\s+variances?|\s+swings?)?$",
        re.IGNORECASE,
    ), "top_percent"),

    (re.compile(
        r"^(?:how\s+many\s+(?:material(?:\s+items?)?|rows?|variances?|line\s+items?)|row\s+count|item\s+count|metrics)\??$",
        re.IGNORECASE,
    ), "metrics_count"),

    (re.compile(
        r"^(?:variance\s+concentration|pareto(?:\s+analysis|\s+distribution)?|concentration(?:\s+of\s+variances?)?|how\s+concentrated\s+are\s+variances)\??$",
        re.IGNORECASE,
    ), "variance_concentration"),

    (re.compile(
        r"^(?:what\s+is\s+unbudgeted|unbudgeted(?:\s+spend|\s+expenses?|\s+items?)|show\s+unbudgeted|zero\s+budget\s+items?)\??$",
        re.IGNORECASE,
    ), "unbudgeted_spend"),

    (re.compile(
        r"^(?:where\s+did\s+we\s+save(?:\s+money)?|cost\s+savings?|expense\s+savings?|favou?rable\s+expenses?|show\s+savings)\??$",
        re.IGNORECASE,
    ), "cost_savings"),

    (re.compile(
        r"^(?:where\s+did\s+revenue\s+(?:fall\s+short|miss)|revenue\s+(?:misses|shortfall)|unfavou?rable\s+revenue|show\s+revenue\s+misses)\??$",
        re.IGNORECASE,
    ), "revenue_misses"),

    (re.compile(
        r"^compare\s+(?P<item1>.+?)\s+(?:and|with|vs\.?|to)\s+(?P<item2>.+)$",
        re.IGNORECASE,
    ), "compare_items"),

    (re.compile(
        r"^(?:set\s+)?(?:thresholds?|materiality)\s+(?:to\s+)?(?P<spec>.+)$",
        re.IGNORECASE,
    ), "set_threshold"),

    (re.compile(
        r"^(?:what\s+if|recalculate|adjust)\s+(?:thresholds?|materiality)"
        r"\s+(?:(?:to|is|was|were|=)\s+)?(?P<spec>.+)$",
        re.IGNORECASE,
    ), "set_threshold"),

    (re.compile(
        r"^(?:what\s+if(?:\s+we)?|simulate|model)\s+"
        r"(?P<direction>increase|increased|raise|grow|cut|cuts|reduce|reduced|drop|drops|boost|expand|shrink)\s+"
        r"(?P<target>.+?)\s+"
        r"(?:by\s+)?"
        r"(?P<amount>[$€£]?[0-9,_.]{1,30}\s*(?:%|[kKmMbB])?)\s*"
        r"(?P<suffix>higher|lower|up|down|more|less)?\s*\??$",
        re.IGNORECASE,
    ), "what_if"),

    (re.compile(
        r"^(?:what\s+if(?:\s+we)?|simulate|model)\s+"
        r"(?P<target>.+?)\s+"
        r"(?:is\s+|are\s+|goes\s+|moves\s+)?"
        r"(?P<direction>increases?|increased?|rises?|drop(?:s|ped)?|decreases?|decreased?|falls?|grows?|growth|grow|climbs?|jumps?|higher|lower|up|down|cuts?|cut|\+|\-)?\s*"
        r"(?:by\s+)?"
        r"(?P<amount>[$€£]?[0-9,_.]{1,30}\s*(?:%|[kKmMbB])?)\s*"
        r"(?P<suffix>higher|lower|up|down|more|less)?\s*\??$",
        re.IGNORECASE,
    ), "what_if"),

    (re.compile(
        r"^(?:show\s+)?(?:the\s+)?sensitivity(?:\s+(?:analysis|matrix|table|model|test))?\??$"
        r"|^(?:scenario\s+analysis|scenarios|stress\s+test)\??$",
        re.IGNORECASE,
    ), "sensitivity"),

    (re.compile(
        r"^(?:what\s+is\s+(?:our\s+)?)?(?:annualized\s+)?run\s*rate(?:\s+(?:projection|forecast|analysis))?\??$"
        r"|^(?:project|forecast)\s+(?:the\s+)?(?:full\s+year|year\s+end|annualized|fy)\??$"
        r"|^(?:full\s+year|year\s+end|annualized)\s+(?:projection|forecast|run\s*rate)\??$"
        r"|^run\s*rate$",
        re.IGNORECASE,
    ), "run_rate"),

    # ── Standard Exploration & Filters ──────────────────────────────
    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?material(?:\s+(?:variances?|items?))?$",
        re.IGNORECASE,
    ), "material"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:(?:work)?sheets?|statements?)\??$"
        r"|^(?:switch|change)\s+(?:(?:work)?sheets?|statements?)\??$"
        r"|^list\s+(?:(?:work)?sheets?|statements?)\??$",
        re.IGNORECASE,
    ), "list_sheets"),

    (re.compile(
        r"^(?:switch\s+(?:to\s+)?)?(?:(?:work)?sheet|statement)\s+(?:to\s+)?(?P<sheet>.+)$",
        re.IGNORECASE,
    ), "switch_sheet"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:unfavou?rable|unfav|adverse|red\s*flags?)"
        r"(?:\s+(?:variances?|items?))?$",
        re.IGNORECASE,
    ), "filter_status_u"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:favou?rable|fav|good\s*news)"
        r"(?:\s+(?:variances?|items?))?$",
        re.IGNORECASE,
    ), "filter_status_f"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:revenue|rev|income|sales)"
        r"(?:\s+(?:variances?|items?|lines?|rows?))?$",
        re.IGNORECASE,
    ), "filter_type_rev"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?(?:expenses?|exp|costs?)"
        r"(?:\s+(?:variances?|items?|lines?|rows?))?$",
        re.IGNORECASE,
    ), "filter_type_exp"),

    (re.compile(
        r"^(?:show\s+)?(?:all\s+)?unclassified"
        r"(?:\s+(?:variances?|items?|lines?|rows?))?$",
        re.IGNORECASE,
    ), "filter_type_unc"),

    (re.compile(
        r"^(?:show\s+)?top\s+(?P<count>\d{1,9})(?:\s+(?P<kind>expenses?|costs?|revenues?|sales|income))?"
        r"(?:\s+(?:variances?|items?|rows?|lines?))?"
        r"(?:\s+by\s+(?:dollars?|amount|value|\$))?$", re.IGNORECASE,
    ), "top_n"),

    (re.compile(
        r"^(?:(?:can\s+you\s+)?(?:why|explain|tell\s+me\s+about|give\s+me\s+(?:more\s+)?color\s+on|dive\s+into|what\s+about)|drivers?|breakdown|decompos\w*|what\s+happened(?:\s+(?:to|with|there|here))?|how\s+come)"
        r"(?:\s+(?:for\s+)?(?:the\s+)?(?P<item>.+))?\s*\??$",
        re.IGNORECASE,
    ), "explain"),

    (re.compile(
        r"^(?:details?|more\s+details?|row|info)"
        r"(?:\s+(?:for\s+)?(?:the\s+)?(?P<item>.+))?\s*\??$"
        r"|"
        r"^(?:show)\s+(?!(?:me|us)\b)(?:for\s+)?(?:the\s+)?(?P<item2>.+)$",
        re.IGNORECASE,
    ), "detail"),

    (re.compile(
        r"^(?:(?:show\s+|are\s+there\s+any\s+)?(?:warnings?|data\s+quality(?:\s+issues?|\s+alerts?)?|quality|issues?|red\s*flags?|anomalies)|any\s+(?:warnings?|issues?|red\s*flags?|data\s+alerts?))\??$",
        re.IGNORECASE,
    ), "warnings"),

    (re.compile(
        r"^(?:recommendations?|actions?|strategic|mitigation|next\s+steps?"
        r"|what\s+should\s+(?:we|management)\s+do"
        r"|what\s+(?:do\s+you\s+recommend|are\s+(?:your\s+)?recommendations?)"
        r"|what\s+actions?\s+should\s+we\s+take"
        r"|how\s+(?:can|do)\s+we\s+(?:fix|address|mitigate)\s+this)\??$",
        re.IGNORECASE,
    ), "recommendations"),

    (re.compile(
        r"^(?:totals?|aggregates?|reconcile|rev(?:enue)?\s+(?:and|&|vs\.?)\s+exp(?:ense)?s?)$",
        re.IGNORECASE,
    ), "totals"),

    (re.compile(
        r"^(?:full\s+)?report$", re.IGNORECASE,
    ), "full_report"),
]


_TRAILING_FILLER = re.compile(r"(?:[\s,]+(?:please|pls|plz|thanks|thank\s+you))+[\s.!?]*$", re.IGNORECASE)
_TRAILING_PUNCTUATION = re.compile(r"(?<=[\w%])[.!?]+$")
# "show me the summary", "can you give us all the expenses": a polite lead-in before a command.
_POLITE_LEAD = re.compile(
    r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?(?P<verb>show|give|get|pull\s+up|bring\s+up)"
    r"\s+(?:me|us)\s+(?:the\s+|our\s+|all\s+(?:the\s+|of\s+the\s+)?)?(?P<rest>.+)$",
    re.IGNORECASE,
)
_CLEANED_CAPTURES = frozenset({"item", "item1", "item2", "sheet"})


def parse_intent(text: str) -> ParsedIntent:
    """Match user text against ordered patterns and return the first hit.

    The text is normalised first (see ``normalize_for_routing``); a message longer than
    ``MAX_ROUTING_CHARS`` (or one padded past ``MAX_RAW_MESSAGE_CHARS``) is the ``too_long``
    intent and is never matched. Trailing filler
    ("please", "thanks") is always ignored; unmatched text is retried without trailing
    punctuation and without a polite lead-in, so "summary please", "Summary?!" and
    "show me the summary" all resolve.
    """
    if len(text) > MAX_RAW_MESSAGE_CHARS:
        return ParsedIntent(intent_id="too_long", captures={})
    text = normalize_for_routing(text)
    if len(text) > MAX_ROUTING_CHARS:
        return ParsedIntent(intent_id="too_long", captures={})
    text = _TRAILING_FILLER.sub("", text).strip() or text
    parsed = _match_intent(text)
    if parsed.intent_id != "unknown":
        return parsed
    for variant in _retry_variants(text):
        retry = _match_intent(variant)
        if retry.intent_id != "unknown":
            return retry
    return parsed


def _retry_variants(text: str) -> list[str]:
    relaxed = _TRAILING_PUNCTUATION.sub("", text).strip()
    variants = [relaxed] if relaxed and relaxed != text else []
    lead = _POLITE_LEAD.match(relaxed or text)
    if lead is not None:
        rest = lead.group("rest").strip()
        variants.append(rest)
        if lead.group("verb").lower() == "show":
            variants.append(f"show {rest}")  # "show me Marketing" -> detail on Marketing
    return variants


def _match_intent(text: str) -> ParsedIntent:
    for pattern, intent_id in _INTENT_PATTERNS:
        match = pattern.match(text)
        if match is not None:
            captures = {
                key: _clean_capture(key, value)
                for key, value in match.groupdict().items()
                if value is not None
            }
            captures = {key: value for key, value in captures.items() if value or key not in _CLEANED_CAPTURES}
            if "item2" in captures and "item1" not in captures:
                captures["item"] = captures.pop("item2")
            return ParsedIntent(intent_id=intent_id, captures=captures)
    return ParsedIntent(intent_id="unknown", captures={"text": text})


def _clean_capture(key: str, value: str) -> str:
    """Item and sheet captures are the rest of the message; drop its trailing '?' and spaces."""
    return value.rstrip("? \t") if key in _CLEANED_CAPTURES else value


def _match_key(value: str) -> str:
    return normalize_for_routing(value).lower()


def find_line_item(
    query: str, line_items: list[str],
) -> list[str]:
    """Deterministic line-item matching: exact, prefix, then substring.

    Strips surrounding quotes, brackets, and trailing question marks.
    Returns a list of matches (empty if none, multiple if ambiguous).
    """
    query_cleaned = _match_key(query).rstrip("?.!").strip("'\"`[]").strip()
    if not query_cleaned:
        return []

    keyed = [(_match_key(item), item) for item in dict.fromkeys(line_items)]

    # 1. Exact match (case-insensitive)
    exact = [item for key, item in keyed if key == query_cleaned]
    if exact:
        return exact

    # 2. Prefix match
    prefix = [item for key, item in keyed if key.startswith(query_cleaned)]
    if prefix:
        return prefix

    # 3. Substring containment
    return [item for key, item in keyed if query_cleaned in key]
