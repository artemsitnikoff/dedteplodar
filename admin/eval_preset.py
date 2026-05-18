"""Preset evaluation dataset — 50 realistic buyer questions for Teplodar products."""

EVAL_DATASET = [
    # ── подбор (product selection) ── 14 questions ──────────────────────────
    {
        "id": 1,
        "question": "посоветуйте печь для бани на 14 кубов",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 2,
        "question": "какой котёл выбрать для дома 100 квадратных метров",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 3,
        "question": "какую печь посоветуете для бани 20 кубометров",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 4,
        "question": "нужна печь для небольшой бани на дровах, что порекомендуете",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 5,
        "question": "какой котёл Куппер подойдёт для 150 кв.м",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 6,
        "question": "хочу отопительную печь для дачи небольшой, что подойдёт",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 7,
        "question": "посоветуйте печь-камин для загородного дома",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 8,
        "question": "какие банные печи есть с баком для воды",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 9,
        "question": "какую печь взять если парная 8 кубов",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 10,
        "question": "что выбрать для отопления деревянного дома 80 кв.м на дровах",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 11,
        "question": "хочу печь с закрытой каменкой для влажной бани",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 12,
        "question": "какие модели печей есть до 30000 рублей",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 13,
        "question": "нужен котёл на дровах и угле для двухэтажного дома",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 14,
        "question": "посоветуйте недорогую банную печь для парной 10 кубов",
        "category": "подбор",
        "expected_type": "RAG_PRODUCT",
    },

    # ── характеристики (specs) ── 11 questions ───────────────────────────────
    {
        "id": 15,
        "question": "сколько весит печь Кадриль",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 16,
        "question": "какой диаметр дымохода у печи Метеор",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 17,
        "question": "какая мощность у котла Куппер ОК 15",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 18,
        "question": "объём топки у Кузбасс 14 ТК",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 19,
        "question": "какой объём парной рассчитана печь Калита",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 20,
        "question": "размеры топки котла Куппер Практик 8",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 21,
        "question": "сколько камней вмещает каменка у Тунгуски",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 22,
        "question": "какая длина дров для Метеора",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 23,
        "question": "КПД котла Куппер Эксперт 22",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 24,
        "question": "из чего сделан корпус печи Кадриль, какая сталь",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 25,
        "question": "сколько весит котёл Куппер ОК 30",
        "category": "характеристики",
        "expected_type": "RAG_PRODUCT",
    },

    # ── установка (installation) ── 10 questions ─────────────────────────────
    {
        "id": 26,
        "question": "нужен ли фундамент под банную печь",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 27,
        "question": "как правильно первый раз растопить новую печь",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 28,
        "question": "какое расстояние должно быть от печи до деревянной стены",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 29,
        "question": "можно ли устанавливать печь самому без мастера",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 30,
        "question": "какой диаметр трубы нужен для монтажа дымохода",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 31,
        "question": "как подключить бак к банной печи",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 32,
        "question": "высота дымохода для нормальной тяги",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 33,
        "question": "нужна ли защита пола под печью",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 34,
        "question": "как чистить дымоход котла Куппер",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 35,
        "question": "можно ли топить печь торфяными брикетами",
        "category": "установка",
        "expected_type": "RAG_PRODUCT",
    },

    # ── компания (company info) ── 8 questions ────────────────────────────────
    {
        "id": 36,
        "question": "какой телефон для заказа",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 37,
        "question": "есть ли доставка по России",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 38,
        "question": "какая гарантия на печи Теплодар",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 39,
        "question": "можно ли купить в рассрочку",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 40,
        "question": "где находится завод Теплодар",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 41,
        "question": "можно ли вернуть печь если не подошла",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 42,
        "question": "как оплатить заказ картой",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 43,
        "question": "сколько лет компания работает",
        "category": "компания",
        "expected_type": "FAQ_COMPANY",
    },

    # ── дилер (dealers by city) ── 7 questions ────────────────────────────────
    {
        "id": 44,
        "question": "есть ли магазин в Красноярске",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 45,
        "question": "где купить печь в Екатеринбурге",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 46,
        "question": "есть ли дилеры в Новосибирске",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 47,
        "question": "хочу купить котёл в Казани, есть магазины",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 48,
        "question": "магазины Теплодар в Москве",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 49,
        "question": "где купить печь в Омске",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 50,
        "question": "есть ли точки продаж в Самаре",
        "category": "дилер",
        "expected_type": "FAQ_DEALER",
    },
]


# ─────────────────────────────────────────────── Mango real-call dataset
# 50 real client questions extracted from April-May 2026 Mango Office
# support call transcripts via Opus analysis. Question IDs start at 101
# to never collide with the synthetic dataset above.
MANGO_EVAL_DATASET = [
    {
        "id": 101,
        "question": "У вас в Тюмени на Пермякова дилер работает?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 102,
        "question": "Если парилка 3х4, высота 2 м, какую газовую печь порекомендуете?",
        "category": "stove_selection_volume",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 103,
        "question": "Можно ли вашим котлом на угле отопить весь дом 1000 м²?",
        "category": "boiler_max_area",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 104,
        "question": "Можно ли перевесить дверцу топки котла Купер 15 2.0, чтобы открывалась в другую сторону?",
        "category": "boiler_door_reverse",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 105,
        "question": "Котёл Русь-18 Про для бани бывает у вас в наличии?",
        "category": "model_availability",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 106,
        "question": "Я правильно попал во Владивостоке?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 107,
        "question": "В Сургуте на кольце Победы 45/1 написано Теплодар, но вывески нет — где находится магазин?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 108,
        "question": "Какую печь брать на парилку ~15 м³ — на 18 или на 24 кубов?",
        "category": "stove_selection_volume",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 109,
        "question": "Бесплатная доставка от какого количества?",
        "category": "delivery_free_conditions",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 110,
        "question": "Подойдёт ли зольник для старой печи Русь-12 с глухой дверкой?",
        "category": "spare_compat",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 111,
        "question": "В Омске у вас филиал есть?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 112,
        "question": "Печка Эльма чисто газовая, не предназначена для другого топлива?",
        "category": "fuel_type",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 113,
        "question": "Можно ли подключить батареи к каминам?",
        "category": "fireplace_heating",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 114,
        "question": "Где в Вышнем Волочке можно купить вашу продукцию?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 115,
        "question": "Сегодня магазины не работают?",
        "category": "store_hours",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 116,
        "question": "В комплект входит переходник для установки пеллетной горелки?",
        "category": "kit_contents",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 117,
        "question": "Шибер из нержавейки лучше, чем из чёрного металла?",
        "category": "material_compare",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 118,
        "question": "Если я оформлю котёл, в какой отдел торгового центра в Бронницах вы доставляете?",
        "category": "delivery_terminal",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 119,
        "question": "Какие сроки изготовления блока парообразователя?",
        "category": "lead_time",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 120,
        "question": "Магазин в Адлере на Авиационной закрылся?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 121,
        "question": "Можно ли заказать печь и регистр без бака, если бак уже есть?",
        "category": "order_customization",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 122,
        "question": "Есть ли аналог печи Тайгинка, кроме Аньки?",
        "category": "discontinued_replacement",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 123,
        "question": "Шесть часов горения — это с регулятором?",
        "category": "burn_duration",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 124,
        "question": "Какая газовая печь подойдёт для бани с парилкой 2 м³?",
        "category": "stove_selection_volume",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 125,
        "question": "В Челябинске есть такие печки по другой цене, можете дать такую же цену?",
        "category": "price_match",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 126,
        "question": "Можно ли заказать у вас одну комплектующую — топливный портал-удлинитель для печи Русь-18?",
        "category": "spare_order",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 127,
        "question": "Какие точные размеры дымохода у котла Куппер ПРО 22?",
        "category": "chimney_diameter",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 128,
        "question": "Сколько будет стоить доставка печи Верона 200 в Сергиев Посадский район?",
        "category": "delivery_cost",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 129,
        "question": "Какой максимально мощный твердотопливный котёл, до 100 кВт?",
        "category": "boiler_max_power",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 130,
        "question": "Нужен ТЭН 6 кВт G1/2, где можно купить в Санкт-Петербурге?",
        "category": "spare_lookup_city",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 131,
        "question": "Доставка котла Куппер ПРО 16 в Геленджик есть?",
        "category": "delivery_region",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 132,
        "question": "Как решить вопрос с доставкой за город, 200 км от Новосибирска?",
        "category": "delivery_remote",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 133,
        "question": "Хочу купить пеллетный котёл и пеллетную горелку, сколько это будет стоить?",
        "category": "pellet_boiler",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 134,
        "question": "Подойдёт ли газовая горелка за 45000 рублей на 40 кВт к котлу Купер ПРО 42?",
        "category": "burner_compat",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 135,
        "question": "Почему газовая печь Эльма-20 отключается через 5-10 минут после запуска?",
        "category": "warranty_issue",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 136,
        "question": "Заказал котёл, пришло письмо что отправлен, но не вижу где он находится — как отследить?",
        "category": "tracking",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 137,
        "question": "Как разобрать кожух печи Русь-18 для замены сгнившей ножки?",
        "category": "repair_instructions",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 138,
        "question": "Можно ли заказать котёл напрямую с завода по цене с сайта?",
        "category": "direct_order",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 139,
        "question": "Какая цена на чугунную печь Верона 200 и как её заказать?",
        "category": "price_check",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 140,
        "question": "Можно ли поменять только защитный металлический чехол на дверке котла Куппер ПРО 36?",
        "category": "spare_partial",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 141,
        "question": "Сколько будет стоить доставка котла Куппер Практик 14 до деревни Волчиха Алтайского края?",
        "category": "delivery_cost",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 142,
        "question": "Скала-12 хватит на парилку 10,5 м³ со стеклянной дверью?",
        "category": "stove_selection_volume",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 143,
        "question": "Есть ли базальтовый фольгированный картон в магазине на Левобережном в Барнауле?",
        "category": "spare_lookup_city",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 144,
        "question": "В Якутске работает магазин Теплодар?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 145,
        "question": "Как происходит оплата и доставка в Кемерово, есть ли в наличии?",
        "category": "order_process",
        "expected_type": "FAQ_COMPANY",
    },
    {
        "id": 146,
        "question": "Сколько метров кабель датчика температуры в комплекте с пультом Комфорт?",
        "category": "spec_detail",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 147,
        "question": "Есть ли филиалы в Красноярске?",
        "category": "dealer_lookup",
        "expected_type": "FAQ_DEALER",
    },
    {
        "id": 148,
        "question": "Можно ли вмонтировать печь в существующий кирпичный трёхходовой дымоход?",
        "category": "installation_question",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 149,
        "question": "Подойдёт ли ящик зольника для Руси-9.1 к старой Руси-9?",
        "category": "spare_compat",
        "expected_type": "RAG_PRODUCT",
    },
    {
        "id": 150,
        "question": "Можно ли оплатить при получении?",
        "category": "payment_terms",
        "expected_type": "FAQ_COMPANY",
    },
]


# Dataset registry — both can be selected from the Eval UI.
# The synthetic set is kept as the default for backward compatibility.
EVAL_DATASETS: dict[str, list[dict]] = {
    "synthetic": EVAL_DATASET,
    "mango":     MANGO_EVAL_DATASET,
}


def get_dataset(name: str | None = None) -> list[dict]:
    """Return the dataset by name. Defaults to synthetic if name is unknown."""
    if not name:
        return EVAL_DATASET
    return EVAL_DATASETS.get(name, EVAL_DATASET)
