from scrapers.alpha_earnings import AlphaEarningsScraper
from scrapers.nasdaq_earnings import NasdaqEarningsScraper
from scrapers.fomc import FOMCScraper
from scrapers.edgar import EdgarScraper
from scrapers.finra_ats import FinraAtsScraper
from scrapers.ibkr_short import IbkrShortScraper

SCRAPERS = {
    "alpha_earnings": AlphaEarningsScraper,
    "nasdaq_earnings": NasdaqEarningsScraper,
    "fomc": FOMCScraper,
    "edgar": EdgarScraper,
    "finra_ats": FinraAtsScraper,
    "ibkr_short": IbkrShortScraper,
}

__all__ = [
    "SCRAPERS",
    "AlphaEarningsScraper",
    "NasdaqEarningsScraper",
    "FOMCScraper",
    "EdgarScraper",
    "FinraAtsScraper",
    "IbkrShortScraper",
]
