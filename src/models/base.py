


class BaseModel:
    

    _code_to_name = None

    @classmethod
    def name_from_code(cls, code):
        """Reverse lookup to get the constant name from a code."""
        if cls._code_to_name is None:
            cls._code_to_name = {
                v: k for k, v in cls.__dict__.items() 
                if not k.startswith('_') and not callable(v)
            }
        return cls._code_to_name.get(code)

    # ...existing code...
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercase, strip, remove accents and collapse non-alnum to single spaces."""
        import unicodedata, re
        if not isinstance(text, str):
            return ""
        s = text.strip()
        # If input like "Ambitos.Estatal", keep only the part after the last dot
        if '.' in s:
            s = s.rsplit('.', 1)[1]
        s = s.lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r'[^0-9a-z]+', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    @classmethod
    def to_constant_name(cls, text: str) -> str:
        """Convert arbitrary text to UPPER_SNAKE_CASE constant name.
        Examples:
          "estatal" -> "ESTATAL"
          "comunidad autonoma" -> "COMUNIDAD_AUTONOMA"
          "Ambitos.Estatal" -> "ESTATAL"
        """
        s = cls._normalize_text(text)
        if not s:
            return ""
        parts = s.split(" ")
        return "_".join(p.upper() for p in parts)

    @classmethod
    def from_string(cls, text: str):
        """Convert a string to the corresponding code (int) defined on this class.
        Returns the code int (e.g. 1 or 2) or None if not found.
        Usage:
          Ambitos.from_string("estatal")           -> 1
          Ambitos.from_string("Ambitos.Estatal")   -> 1
          Ambitos.from_string("comunidad autonoma")-> getattr(Ambitos, "COMUNIDAD_AUTONOMA", None)
        """
        name = cls.to_constant_name(text)
        if not name:
            return None
        return getattr(cls, name, None)
