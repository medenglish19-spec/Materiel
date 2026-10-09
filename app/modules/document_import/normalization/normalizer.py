import re, unicodedata
_TRANSLATION=str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ى":"ي","ة":"ه","ـ":"","٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9"})
def normalize_text(value):
 if not value:return ""
 value=unicodedata.normalize("NFKC",str(value)).translate(_TRANSLATION).casefold()
 value=re.sub(r"[\u064b-\u065f\u0670]","",value)
 return " ".join(re.sub(r"[^\w]+"," ",value,flags=re.UNICODE).split())
def normalize_value(value):
 return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",str(value or "")).strip())[:255]
