"""Tool schemas for the Titatu WordPress read bridge."""

TOOLSET = "titatu-wp"

WP_BRIDGE_HEALTH = {
    "name": "wp_bridge_health",
    "description": "Check WordPress connection health for Titatu quotes. Call when asked if WP is connected.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GET_BID = {
    "name": "get_bid",
    "description": "Fetch one quote/bid by numeric WordPress ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "WordPress bid post ID"},
        },
        "required": ["id"],
    },
}

SEARCH_BIDS = {
    "name": "search_bids",
    "description": "Free-text search in Titatu quotes (title/content).",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text"},
            "per_page": {"type": "integer", "description": "Max results, default 20"},
        },
        "required": ["query"],
    },
}

FIND_BIDS = {
    "name": "find_bids",
    "description": "Fuzzy find quotes by customer name, phone, and/or email. If several matches, return candidates for user confirmation.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Customer or event name"},
            "phone": {"type": "string", "description": "Phone number"},
            "email": {"type": "string", "description": "Email"},
        },
        "required": [],
    },
}

LIST_BIDS_BY_QUOTE_STATUS = {
    "name": "list_bids_by_quote_status",
    "description": "List quotes by real JetEngine bid_status: approved (אושר), waiting (ממתין), not_approved (לא אושר).",
    "parameters": {
        "type": "object",
        "properties": {
            "quote_status": {
                "type": "string",
                "enum": ["approved", "waiting", "not_approved"],
                "description": "approved / waiting / not_approved",
            },
            "days": {"type": "integer", "description": "Lookback days, default 31"},
        },
        "required": ["quote_status"],
    },
}

LIST_APPROVED_TODAY = {
    "name": "list_approved_today",
    "description": "List quotes whose bid_status is אושר and were modified today (Israel time).",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

LIST_STANDS = {
    "name": "list_stands",
    "description": "List stand catalog (services + estimate_stand). Uses memory/disk cache if WordPress is down.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GET_STAND = {
    "name": "get_stand",
    "description": "Fetch one stand by WordPress ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "Stand post ID"},
        },
        "required": ["id"],
    },
}

SEARCH_STANDS = {
    "name": "search_stands",
    "description": "Search stands by title / product_title text.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text"},
        },
        "required": ["query"],
    },
}

START_QUOTE_INTAKE = {
    "name": "start_quote_intake",
    "description": "Start the fixed Titatu quote questionnaire. Call when the user wants to create a new quote. Reply with the tool's say field verbatim.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SUBMIT_INTAKE_MESSAGE = {
    "name": "submit_intake_message",
    "description": "Continue the active quote questionnaire. Pass a clear Hebrew version of the user's intent (fix typos, keep meaning). Never treat conversation like 'תמשיך רק עם השווארמה' as a stand name. Then reply with say verbatim. If use_clarify is true, call clarify with those exact choices (מאושר/לא מאושר for yes/no).",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Normalized Hebrew intent, not a raw typo dump"},
        },
        "required": ["text"],
    },
}

RESOLVE_STANDS = {
    "name": "resolve_stands",
    "description": "Map free-text Hebrew stand names to catalog IDs with fuzzy matching. Ask the user if several candidates are close.",
    "parameters": {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Stand names as the user said them",
            },
        },
        "required": ["names"],
    },
}

GET_LAST_BID = {
    "name": "get_last_bid",
    "description": "Return the last quote this chat created (id, title, live link). Use when the user says the last quote / זו / אותה without an id.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

TRASH_BID = {
    "name": "trash_bid",
    "description": "Move a Titatu quote to WordPress trash. NEVER call this until the user tapped מאושר on the delete preview. If the user says מחק, use submit_intake_message with מחק instead so they get a confirmation card.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "WordPress bid ID. Omit to use the last quote."},
        },
        "required": [],
    },
}

UPDATE_QUOTE = {
    "name": "update_quote",
    "description": "Update a live Titatu quote: guests, price-per-diner, decorated stands, add food stands, title, phone, date, address, serve time. Omit id to use the last quote.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "WordPress bid ID. Omit to use the last quote."},
            "title": {"type": "string"},
            "guests": {"type": "string", "description": "Guest count"},
            "show_price_per_participants": {
                "type": "boolean",
                "description": "true = show price per diner (מחיר לסועד)",
            },
            "decorated_stands": {
                "type": "boolean",
                "description": "true = allow decorated stands (עמדות מעוצבות)",
            },
            "add_stands": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Food stand names to add",
            },
            "phone": {"type": "string"},
            "event_date": {"type": "string"},
            "address": {"type": "string"},
            "serve_time": {"type": "string"},
        },
        "required": [],
    },
}
