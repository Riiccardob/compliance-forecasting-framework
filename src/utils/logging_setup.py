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

        Parameters
        ----------
        name:
            Nome del logger (tipicamente __name__ del modulo chiamante).
        level:
            Livello di log come stringa (es. "INFO", "DEBUG", "WARNING").

        Returns
        -------
        logging.Logger
            Logger configurato con handler su stderr e formato standard.
        """
        logger = logging.getLogger(name)
        if level.upper() not in LoggingSetup._VALID_LEVELS:
            raise ValueError(
                f"Livello di log non valido: '{level}'. "
                f"Valori accettati: {sorted(LoggingSetup._VALID_LEVELS)}"
            )
        logger.setLevel(getattr(logging, level.upper()))
        logger.propagate = False

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(LoggingSetup._FORMAT))
            logger.addHandler(handler)

        return logger
