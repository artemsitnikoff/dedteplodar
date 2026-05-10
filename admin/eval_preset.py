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
