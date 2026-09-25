const COMMON_PHONETIC_WORDS = {
  ram: 'राम',
  ramesh: 'रमेश',
  mohan: 'मोहन',
  ashok: 'अशोक',
  kumar: 'कुमार',
  paraspur: 'परसपुर',
  unnao: 'उन्नाव',
  safipur: 'सफीपुर',
  dog: 'डॉग',
};

const CONSONANTS = [
  ['chh', 'छ'], ['ksh', 'क्ष'], ['shr', 'श्र'], ['ng', 'ङ'], ['ny', 'ञ'],
  ['kh', 'ख'], ['gh', 'घ'], ['ch', 'च'], ['jh', 'झ'], ['th', 'थ'], ['dh', 'ध'], ['ph', 'फ'], ['bh', 'भ'], ['sh', 'श'],
  ['k', 'क'], ['g', 'ग'], ['j', 'ज'], ['t', 'त'], ['d', 'द'], ['n', 'न'], ['p', 'प'], ['b', 'ब'], ['m', 'म'], ['y', 'य'], ['r', 'र'], ['l', 'ल'], ['v', 'व'], ['w', 'व'], ['s', 'स'], ['h', 'ह'], ['f', 'फ़'], ['z', 'ज़'], ['q', 'क'], ['x', 'क्स'],
];

const VOWELS = [
  ['ai', ['ऐ', 'ै']], ['au', ['औ', 'ौ']], ['aa', ['आ', 'ा']], ['ii', ['ई', 'ी']], ['ee', ['ई', 'ी']], ['uu', ['ऊ', 'ू']], ['oo', ['ऊ', 'ू']],
  ['a', ['अ', '']], ['i', ['इ', 'ि']], ['u', ['उ', 'ु']], ['e', ['ए', 'े']], ['o', ['ओ', 'ो']],
];

const readToken = (value, index, candidates) => candidates.find(([roman]) => value.startsWith(roman, index));

/**
 * Converts a single Roman token with deterministic phonetic rules. It is not a
 * translator: unsupported input is returned unchanged so officer edits remain safe.
 */
export function transliterateRomanToken(token) {
  if (!/^[A-Za-z]+$/.test(token)) return token;
  const roman = token.toLowerCase();
  if (COMMON_PHONETIC_WORDS[roman]) return COMMON_PHONETIC_WORDS[roman];

  let output = '';
  let index = 0;
  while (index < roman.length) {
    const vowel = readToken(roman, index, VOWELS);
    if (vowel) {
      output += vowel[1][0];
      index += vowel[0].length;
      continue;
    }

    const consonant = readToken(roman, index, CONSONANTS);
    if (!consonant) return token;
    output += consonant[1];
    index += consonant[0].length;

    const followingVowel = readToken(roman, index, VOWELS);
    if (followingVowel) {
      output += followingVowel[1][1];
      index += followingVowel[0].length;
    } else if (index < roman.length) {
      output += '्';
    }
  }
  return output || token;
}

const EXCLUDED_LABEL = /khata|gata|khasra|number|serial|code|year|date|area|share|revenue|identifier|id/i;
const TEXT_LABEL = /district|tehsil|village|pargana|holder|khatedar|guardian|father|husband|name|remarks?|comment|note|residence|address|patwari|lekhpal|land type|irrigation/i;

export function supportsHindiPhoneticInput(label) {
  const text = String(label || '');
  return !EXCLUDED_LABEL.test(text) && TEXT_LABEL.test(text);
}
