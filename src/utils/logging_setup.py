"""Configurazione del logging per i moduli del framework."""
import logging


class LoggingSetup:
    """Factory per la creazione di logger nominati con formato standard."""

    _FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    _VALID_LEVELS: frozenset[str] = frozenset(
        {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    )

    @staticmethod
    def configure(name: str, level: str) -> logging.Logger:
        """Crea e restituisce un logger configurato con il formato standard.

        Il metodo è idempotente: se il logger esiste già (handler presenti),
        lo restituisce invariato senza modificare né il livello né gli handler.

        Parameters
        ----------
        name:
            Nome del logger (tipicamente __name__ del modulo chiamante).
        level:
            Livello di log come stringa (es. "INFO", "DEBUG", "WARNING").
            Ignorato se il logger è già configurato.

        Returns
        -------
        logging.Logger
            Logger configurato.
        """
        if level.upper() not in LoggingSetup._VALID_LEVELS:
            raise ValueError(
                f"Livello di log non valido: '{level}'. "
                f"Valori accettati: {sorted(LoggingSetup._VALID_LEVELS)}"
            )
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(getattr(logging, level.upper()))
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(LoggingSetup._FORMAT))
            logger.addHandler(handler)
            logger.propagate = False
        return logger
