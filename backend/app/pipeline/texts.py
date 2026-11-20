"""Fixed user-facing texts (EN / Roman Urdu). Used for refusals, errors and template fallbacks."""

TEXTS: dict[str, dict[str, str]] = {
    "help": {
        "english": "I'm Briha, your company data assistant. I can tell you about **reel cutting**, **sales** and "
                   "**stock**: by date, paper type, GSM and size. Try:\n- How many sheets were cut today?\n"
                   "- Kal 23x36 art paper kitna bika?\n- Bleach card ka stock kitna hai?",
        "roman_urdu": "Main Briha hoon, aap ka company data assistant. Main **cutting**, **sale** aur **stock** ke "
                      "baare mein bata sakta hoon: date, paper type, GSM aur size ke hisaab se. Maslan:\n"
                      "- Aaj kitne papers kate aur kitne bike?\n- Pichle hafte size wise cutting\n"
                      "- Bleach card ka stock kitna hai?",
    },
    "language_set": {
        "english": "Sure, I'll answer in English from now on.",
        "roman_urdu": "Theek hai, ab se main Roman Urdu mein jawab doonga.",
    },
    "conversation_fallback": {
        "english": "I can't answer that from this chat. I can tell you about **reel cutting**, **sales** and "
                   "**stock**: just ask the question you need.",
        "roman_urdu": "Is chat se main iska jawab nahi de sakta. Main **cutting**, **sale** aur **stock** ke baare "
                      "mein bata sakta hoon: jo sawal chahiye woh pooch lein.",
    },
    "write_request": {
        "english": "I can only read data, not change it. Please use the ERP for updates.",
        "roman_urdu": "Main sirf data dekh aur bata sakta hoon, koi change nahi kar sakta. Update ke liye ERP use karein.",
    },
    "out_of_scope": {
        "english": "I only help with the company's cutting, sales and stock data, and I don't make forecasts. "
                   "You could ask, for example: \"How much was sold last month?\"",
        "roman_urdu": "Main sirf company ki cutting, sale aur stock ke data mein madad karta hoon, forecast "
                      "nahi karta. Maslan poochein: \"Pichle mahine kitna bika?\"",
    },
    "future": {
        "english": "That date is in the future. I can only report recorded data up to today.",
        "roman_urdu": "Ye date future ki hai. Main sirf aaj tak ka record shuda data bata sakta hoon.",
    },
    "range_too_long": {
        "english": "That range is longer than one year. Please choose a shorter period.",
        "roman_urdu": "Range 1 saal se zyada hai, thoda chhota period batayein.",
    },
    "bad_date": {
        "english": "I couldn't understand the date. Which day or period do you mean?",
        "roman_urdu": "Date samajh nahi aayi. Kaunsa din ya period chahiye?",
    },
    "assumed_today": {
        "english": "No date was given, so this is today's data.",
        "roman_urdu": "Date nahi batayi thi, is liye aaj ka data dikhaya hai.",
    },
    "bad_gsm": {
        "english": "That GSM doesn't look right. Please check it.",
        "roman_urdu": "Ye GSM sahi nahi lag raha. Dobara check karein.",
    },
    "bad_size": {
        "english": "I couldn't read the size \"{value}\". Please write it like 23x36.",
        "roman_urdu": "Size \"{value}\" samajh nahi aaya. Is tarah likhein: 23x36.",
    },
    "which_entity": {
        "english": "Which {kind} do you mean?",
        "roman_urdu": "Kaunsa {kind}?",
    },
    "unknown_entity": {
        "english": "I couldn't find the {kind} \"{value}\". Did you mean one of these?",
        "roman_urdu": "{kind} \"{value}\" nahi mila. Kya aap ka matlab in mein se koi hai?",
    },
    "which_metric": {
        "english": "Do you mean cut or sold?",
        "roman_urdu": "Aap kaata hua poochh rahe hain ya bika hua?",
    },
    # The data BRIHA has does not answer this question (e.g. pending orders): say so plainly.
    "no_matching_data": {
        "english": "I don't have data that answers this question, so I won't guess. I can tell you about "
                   "completed cutting, sales, and current stock. Try asking about one of those.",
        "roman_urdu": "Mere paas is sawal ka data nahi hai, is liye main andaza nahi lagaunga. Main kati hui "
                      "cutting, sales aur maujooda stock ke baare mein bata sakta hoon. Un mein se kuch poochein.",
    },
    # The data came back but failed BRIHA's own checks: never show possibly wrong numbers.
    "data_check_failed": {
        "english": "The data I got for this question didn't pass my checks, so I won't show numbers that might be "
                   "wrong. Please try again in a moment. If it keeps happening, let your admin know.",
        "roman_urdu": "Is sawal ka jo data mila woh mere checks mein theek nahi nikla, is liye main ghalat ho sakne "
                      "wale numbers nahi dikhaunga. Thodi der baad dobara try karein. Baar baar ho to admin ko batayein.",
    },
    "DATA_SOURCE_UNAVAILABLE": {
        "english": "The company data system isn't responding. Please try again shortly.",
        "roman_urdu": "Abhi company ka data system jawab nahi de raha. Thodi der baad try karein.",
    },
    "DATA_SOURCE_TIMEOUT": {
        "english": "The company data system took too long. Please try again shortly.",
        "roman_urdu": "Company ka data system bohat der laga raha hai. Thodi der baad try karein.",
    },
    "LLM_UNAVAILABLE": {
        "english": "BRIHA is busy right now. Please try again shortly.",
        "roman_urdu": "BRIHA abhi busy hai, thodi der baad try karein.",
    },
    "TIMEOUT": {
        "english": "This took too long. Please try again.",
        "roman_urdu": "Is mein bohat der lag gayi. Dobara try karein.",
    },
    "INTERNAL": {
        "english": "Something went wrong. Please try again.",
        "roman_urdu": "Kuch masla ho gaya. Dobara try karein.",
    },
}

KIND_NAMES = {
    "paper_type": {"english": "paper type", "roman_urdu": "paper type"},
    "customer": {"english": "customer", "roman_urdu": "customer"},
    "warehouse": {"english": "warehouse", "roman_urdu": "godown"},
}


def t(key: str, language: str, **kwargs: str) -> str:
    lang = language if language in ("english", "roman_urdu") else "english"
    return TEXTS[key][lang].format(**kwargs)
