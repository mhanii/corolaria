from .base import BaseModel
class Ambitos(BaseModel):
    """Data model for BOE auxiliary data.

    Generated from: https://www.boe.es/datosabiertos/api/datos-auxiliares/ambitos
    """
    AUTONOMICO = 2
    ESTATAL = 1



if __name__ == "__main__":
    # Simple test
    print(Ambitos.AUTONOMICO)  # Output: 2
    print(Ambitos.name_from_code(2))  # Output: ESTATAL