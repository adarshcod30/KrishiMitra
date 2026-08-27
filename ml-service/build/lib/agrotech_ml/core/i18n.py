from __future__ import annotations

from typing import Any

from agrotech_ml.models.schemas import LanguageCode


LANGUAGE_LABELS: dict[LanguageCode, str] = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "te": "Telugu",
    "ta": "Tamil",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
}


CROP_NAME_TRANSLATIONS: dict[LanguageCode, dict[str, str]] = {
    "en": {},
    "hi": {
        "rice": "Dhan",
        "maize": "Makka",
        "chickpea": "Chana",
        "cotton": "Kapas",
        "wheat": "Gehu",
        "banana": "Kela",
    },
    "bn": {"rice": "Dhan", "maize": "Bhoota", "banana": "Kola"},
    "te": {"rice": "Vari", "maize": "Mokka Jonna", "banana": "Arati"},
    "ta": {"rice": "Nel", "maize": "Makkacholam", "banana": "Vazhai"},
    "mr": {"rice": "Bhat", "maize": "Makka", "banana": "Keli"},
    "gu": {"rice": "Chokha", "maize": "Makai", "banana": "Kela"},
    "kn": {"rice": "Akki", "maize": "Mekke Jola", "banana": "Balehannu"},
    "ml": {"rice": "Nellu", "maize": "Cholam", "banana": "Vazha"},
    "pa": {"rice": "Dhaan", "maize": "Makka", "banana": "Kela"},
    "or": {"rice": "Dhana", "maize": "Maka", "banana": "Kadali"},
}


I18N_TEXT: dict[str, dict[LanguageCode, str]] = {
    "validate_soil": {
        "en": "Validate soil readings with a fresh lab sample before full-area sowing.",
        "hi": "Puri khet mein bowaai se pehle nayi lab report se mitti data verify karein.",
        "bn": "Puro jomite chash er age notun lab report diye mati data check korun.",
        "te": "Purna polam lo vithanam mundu kotta lab report tho soil values check cheyyandi.",
        "ta": "Muzhu nilaththil vidai seyyum mun puthiya lab report moolam mann nilaiyai sari paarungal.",
        "mr": "Sampurna shetat perani purvi navin lab report ne matti maapdand tapasa.",
        "gu": "Pura khetar ma vavani pela navi lab report thi mati na aakda verify karo.",
        "kn": "Sampoorna holadalli beeja haakuvudakke munche hosa lab report inda matti data verify madi.",
        "ml": "Motham krishiyidathil vithanam mumbayi puthiya lab report upayogichu mann data urappakkuka.",
        "pa": "Puri kheti ton pehlan navi lab report naal mitti data verify karo.",
        "or": "Sampurna khetre beej ropan purbaru nua lab report dwara mati data janch karantu.",
    },
    "fertigation_log": {
        "en": "Prepare a weekly fertigation and irrigation log for the first 30 days after planting.",
        "hi": "Ropan ke baad pehle 30 din ke liye haftewar paani aur poshak input ka record banayein.",
        "bn": "Roponer por prothom 30 diner jonno saptahik pani o poshok log rakhun.",
        "te": "Naatu taruvata modati 30 rojulu varam varam neeru mariyu poshaka log maintain cheyyandi.",
        "ta": "Nadavu pin mudhal 30 naatkalukku vaaranthira neer matrum poshana padhivu vaithirungal.",
        "mr": "Lavninantar pahilya 30 divsat aathvadyacha pani ani poshan nondi theva.",
        "gu": "Ropan pachi pehla 30 divas mate saptaahik paani ane poshan no log banavo.",
        "kn": "Nettina nantara modala 30 dinagalige vaarada neeru mattu poshaka log nirvahisi.",
        "ml": "Nadathiyathinu sesham aadya 30 divasam weekly neerum poshakam log undakkuka.",
        "pa": "Ropai to baad pehle 30 dina lai haftewar paani te poshan da record rakho.",
        "or": "Ropan pare pratham 30 dina paain saptahik pani o poshak log prastut karantu.",
    },
    "pilot_patch": {
        "en": "Run a small pilot patch for {crop} first, then scale after 2-3 week field validation.",
        "hi": "Pehle {crop} ka chhota pilot plot lagayein, 2-3 hafte ke field validation ke baad badhayein.",
        "bn": "Age {crop} diye chhoto pilot plot korun, 2-3 soptaho por fol dekhe boro korun.",
        "te": "Munduga {crop} to chinna pilot patch try chesi, 2-3 vaaralu tarvata scale cheyyandi.",
        "ta": "Mudhalil {crop} siria pilot pagudiyil seithu, 2-3 vaaram pin perukkavum.",
        "mr": "Adhi {crop} sathi chhota pilot plot kara, 2-3 athvadyanantar vistar kara.",
        "gu": "Pehla {crop} mate nanakdu pilot plot karo, 2-3 hafta pachi scale karo.",
        "kn": "Modalu {crop} ge chikka pilot patch maadi, 2-3 vaaragala nantara vistara madi.",
        "ml": "Mumbayi {crop} nte cheriya pilot patch cheythu, 2-3 aazhcha kazhinju valarthuka.",
        "pa": "Pehlaan {crop} da chhota pilot plot lao, 2-3 hafte baad vadda karo.",
        "or": "Prathame {crop} ra chhota pilot plot karantu, 2-3 saptaha pare bruddhi karantu.",
    },
    "irrigation_note": {
        "en": "Irrigation interval is adapted to rainfall and crop water demand.",
        "hi": "Sinchai antaral barsaat aur fasal ki paani ki jarurat ke hisab se diya gaya hai.",
        "bn": "Brishti ebong fosholer pani chahida onujayi sinchai somoy nirdharito.",
        "te": "Varsham mariyu pantaki kavalsina neeru adharanga irrigation interval set chesaru.",
        "ta": "Mazhai matrum payir thanneer thevai adharamaaga sinchai idai velai amaikkappattulladhu.",
        "mr": "Paus ani pikasathi paani garaj yavar adharit sinchan antar thevle aahe.",
        "gu": "Varsad ane pak ni paani jaruriyat pramane sinchai interval set karyo chhe.",
        "kn": "Male mattu beley neerina avashyakathe adharisi sinchana madhya virama nirdhariside.",
        "ml": "Mazhayum krishi neer avashyamum anusarikku sinchanam interval nirdharichu.",
        "pa": "Barsaat te fasal di paani lod mutabik sinchai da antar rakheya gaya hai.",
        "or": "Brusti o fasalar pani darkar anusare sinchan antar nirdharita.",
    },
}


def tr(language: LanguageCode, key: str, **kwargs: Any) -> str:
    text = I18N_TEXT.get(key, {}).get(language) or I18N_TEXT.get(key, {}).get("en") or key
    if kwargs:
        return text.format(**kwargs)
    return text


def localize_crop_name(crop: str, language: LanguageCode) -> str:
    normalized = crop.strip().lower()
    return CROP_NAME_TRANSLATIONS.get(language, {}).get(normalized, crop)
