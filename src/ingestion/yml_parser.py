"""YML parser for Yandex Market format."""

import logging
from typing import List, Generator
from lxml import etree
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert

from ..core.database import get_session
from ..products.models import Category, Product, ProductParam
from ..products.schemas import YMLCategory, YMLOffer, YMLParam
from ..core.config import settings

logger = logging.getLogger(__name__)


class YMLParser:
    """Parser for Yandex YML format."""

    def __init__(self):
        self.session: Session | None = None

    def parse_categories(self, yml_path: str) -> List[YMLCategory]:
        """Parse categories from YML file."""
        categories = []

        try:
            context = etree.iterparse(yml_path, events=('start', 'end'), encoding='utf-8')
            context = iter(context)
            event, root = next(context)

            for event, elem in context:
                if event == 'end' and elem.tag == 'category':
                    category_id = int(elem.get('id'))
                    parent_id = elem.get('parentId')
                    parent_id = int(parent_id) if parent_id else None
                    name = elem.text.strip() if elem.text else ""

                    categories.append(YMLCategory(
                        id=category_id,
                        name=name,
                        parent_id=parent_id
                    ))

                    elem.clear()

        except Exception as e:
            logger.error(f"Error parsing categories: {e}")
            raise

        logger.info(f"Parsed {len(categories)} categories")
        return categories

    def parse_offers(self, yml_path: str) -> Generator[YMLOffer, None, None]:
        """Parse offers from YML file using streaming approach."""
        try:
            context = etree.iterparse(yml_path, events=('start', 'end'), encoding='utf-8')
            context = iter(context)
            event, root = next(context)

            current_offer = None
            current_params = []

            for event, elem in context:
                if event == 'start' and elem.tag == 'offer':
                    current_offer = {
                        'id': int(elem.get('id')),
                        'available': elem.get('available', 'false').lower() == 'true',
                        'params': []
                    }
                    current_params = []

                elif event == 'end' and elem.tag == 'offer' and current_offer:
                    current_offer['params'] = current_params

                    try:
                        offer = YMLOffer(**current_offer)
                        yield offer
                    except Exception as e:
                        logger.warning(f"Error creating offer {current_offer.get('id')}: {e}")

                    current_offer = None
                    current_params = []
                    elem.clear()

                elif event == 'end' and current_offer and elem.text:
                    text = elem.text.strip()

                    if elem.tag == 'url':
                        current_offer['url'] = text
                    elif elem.tag == 'price':
                        try:
                            current_offer['price'] = float(text)
                        except ValueError:
                            pass
                    elif elem.tag == 'currencyId':
                        current_offer['currency_id'] = text
                    elif elem.tag == 'vendor':
                        current_offer['vendor'] = text
                    elif elem.tag == 'manufacturer_warranty':
                        current_offer['manufacturer_warranty'] = text.lower() == 'true'
                    elif elem.tag == 'country_of_origin':
                        current_offer['country_of_origin'] = text
                    elif elem.tag == 'model':
                        current_offer['model'] = text
                    elif elem.tag == 'categoryId':
                        try:
                            current_offer['category_id'] = int(text)
                        except ValueError:
                            pass
                    elif elem.tag == 'picture':
                        current_offer['picture'] = text
                    elif elem.tag == 'name':
                        current_offer['name'] = text
                    elif elem.tag == 'description':
                        current_offer['description'] = text
                    elif elem.tag == 'param':
                        param_name = elem.get('name', '')
                        if param_name and text:
                            current_params.append(YMLParam(name=param_name, value=text))

                    elem.clear()

        except Exception as e:
            logger.error(f"Error parsing offers: {e}")
            raise

    def save_categories(self, categories: List[YMLCategory]) -> None:
        """Save categories to database with upsert logic."""
        if not categories:
            return

        for session in get_session():
            try:
                # Use SQLite upsert (INSERT OR REPLACE)
                for category in categories:
                    stmt = insert(Category).values(
                        id=category.id,
                        name=category.name,
                        parent_id=category.parent_id
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['id'],
                        set_=dict(
                            name=stmt.excluded.name,
                            parent_id=stmt.excluded.parent_id
                        )
                    )
                    session.execute(stmt)

                session.commit()
                logger.info(f"Saved {len(categories)} categories")

            except Exception as e:
                logger.error(f"Error saving categories: {e}")
                session.rollback()
                raise

    def save_offers(self, offers: Generator[YMLOffer, None, None]) -> int:
        """Save offers to database with upsert logic."""
        saved_count = 0

        for session in get_session():
            try:
                for offer in offers:
                    # Upsert product
                    product_stmt = insert(Product).values(
                        id=offer.id,
                        url=offer.url,
                        name=offer.name,
                        model=offer.model,
                        price=offer.price,
                        currency=offer.currency_id,
                        vendor=offer.vendor,
                        country_of_origin=offer.country_of_origin,
                        manufacturer_warranty=offer.manufacturer_warranty,
                        category_id=offer.category_id,
                        picture_url=offer.picture,
                        description=offer.description
                    )

                    product_stmt = product_stmt.on_conflict_do_update(
                        index_elements=['id'],
                        set_=dict(
                            url=product_stmt.excluded.url,
                            name=product_stmt.excluded.name,
                            model=product_stmt.excluded.model,
                            price=product_stmt.excluded.price,
                            currency=product_stmt.excluded.currency,
                            vendor=product_stmt.excluded.vendor,
                            country_of_origin=product_stmt.excluded.country_of_origin,
                            manufacturer_warranty=product_stmt.excluded.manufacturer_warranty,
                            category_id=product_stmt.excluded.category_id,
                            picture_url=product_stmt.excluded.picture_url,
                            description=product_stmt.excluded.description,
                            updated_at=product_stmt.excluded.updated_at
                        )
                    )
                    session.execute(product_stmt)

                    # Delete old params and insert new ones
                    session.query(ProductParam).filter(ProductParam.product_id == offer.id).delete()

                    # Insert new params
                    for param in offer.params:
                        param_stmt = insert(ProductParam).values(
                            product_id=offer.id,
                            name=param.name,
                            value=param.value
                        )
                        session.execute(param_stmt)

                    saved_count += 1

                    if saved_count % 50 == 0:
                        session.commit()
                        logger.info(f"Processed {saved_count} products...")

                session.commit()
                logger.info(f"Saved total {saved_count} products with parameters")

            except Exception as e:
                logger.error(f"Error saving offers: {e}")
                session.rollback()
                raise

        return saved_count

    def run(self, yml_path: str | None = None) -> dict:
        """Run full YML parsing pipeline."""
        if yml_path is None:
            yml_path = str(settings.yandex_yml_path)

        logger.info(f"Starting YML parsing from {yml_path}")

        # Parse and save categories
        categories = self.parse_categories(yml_path)
        self.save_categories(categories)

        # Parse and save offers
        offers = self.parse_offers(yml_path)
        products_count = self.save_offers(offers)

        result = {
            'categories_count': len(categories),
            'products_count': products_count,
            'yml_file': yml_path
        }

        logger.info(f"YML parsing completed: {result}")
        return result