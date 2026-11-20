import type { Language, Stage } from "./types";

const T = {
  english: {
    placeholder: "Ask about cutting, sales or stock…",
    stages: {
      understanding: "Understanding your question",
      retrieving: "Fetching data",
      validating: "Checking the data",
      responding: "Writing the answer",
    },
    verified: "Verified from company data",
    retry: "Try again",
    offline: "No internet connection",
    stop: "Stop",
    whatWrong: "What was wrong?",
    send: "Send",
  },
};

export const STAGES: Stage[] = ["understanding", "retrieving", "validating", "responding"];

// The interface is English only. BRIHA still answers in the language the user asks in.
export function tr(_lang?: Language | null) {
  return T.english;
}

/** Same heuristic as the backend, used before the server tells us the language. */
export function guessLanguage(text: string): Language {
  return /\b(kitna|kitne|kitni|hai|hain|aaj|kal|ka|ki|ke|mein|kya|bika|bike|kata|kate|karo|kar|batao|aur|tha)\b/i.test(
    text,
  )
    ? "roman_urdu"
    : "english";
}

export const SUGGESTIONS = [
  "How many sheets were cut today?",
  "How many sheets were cut and sold today?",
  "Show last week's cutting size wise",
  "How much 23x36 art paper was sold yesterday?",
  "How much stock of bleach card do we have?",
  "Total sales last month",
];
