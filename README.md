# Моделювання поширення атмосферного забруднення та оцінювання економічної ефективності заходів зі зменшення викидів

Навчальна програма першого етапу семестрового проєкту. Вона рахує приземну концентрацію речовини від одного стаціонарного точкового джерела, показує зону перевищення заданого рівня і порівнює навчальні грошові наслідки кількох сценаріїв скорочення викидів.

Це спрощена гаусова модель. Її результати не є офіційною екологічною експертизою, гігієнічним нормативом чи оцінкою збитків.

## Встановлення

Потрібен Python 3.11 або новіша стабільна версія. Команди нижче розраховані на macOS і Linux; у Windows віртуальне середовище активують файлом `.venv\Scripts\activate`.

```bash
cd environmental-pollution-model
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Файл `.env` потрібен лише для OpenAQ і необов’язкових адрес API. Розрахунок шлейфу запускається і без нього.

## Запуск

```bash
streamlit run app.py
```

Після запуску інтерфейс відкривається за адресою <http://localhost:8501>.
На одній сторінці: ключові показники, графіки перевищення, карта приземної концентрації, профіль шлейфу та гаусова формула. Параметри задаються в бічній панелі.

Висновок для захисту першого етапу (з розрахунками): [docs/defense_conclusion.md](docs/defense_conclusion.md) і Word-файл [docs/defense_conclusion.docx](docs/defense_conclusion.docx).

Тести і перевірка стилю:

```bash
pytest
ruff check .
```

## Приклад використання

1. Задайте параметри в бічній панелі.
2. На головній сторінці перегляньте максимум, частку території, зону перевищення і навчальний збиток.
3. Нижче — карта приземної концентрації, профіль уздовж осі шлейфу та формула гаусової моделі.
4. Карта й показники відповідають базовому сценарію без зменшення викидів.

Усі початкові числа в репозиторії мають мітку synthetic: вони не описують конкретне підприємство чи місто.

## Структура

```text
environmental-pollution-model/
├── app.py
├── pyproject.toml
├── requirements.txt
├── .env.example
├── data/
│   ├── sample_input.csv
│   └── sample_scenarios.csv
├── docs/
│   ├── project_statement.md
│   ├── defense_conclusion.md
│   ├── defense_conclusion.docx
│   ├── data_sources.md
│   ├── mathematical_model.md
│   └── assumptions_and_limitations.md
├── src/
│   ├── config.py
│   ├── models/
│   │   ├── gaussian_plume.py
│   │   ├── economic_model.py
│   │   └── scenario.py
│   ├── services/
│   │   ├── open_meteo_client.py
│   │   └── openaq_client.py
│   ├── visualization/
│   │   ├── concentration_map.py
│   │   ├── charts.py
│   │   └── overview.py
│   └── utils/
│       ├── units.py
│       └── validation.py
└── tests/
```

Математика, грошова модель і клієнти API не залежать від Streamlit. `app.py` лише збирає параметри, викликає розрахунок і показує графіки.

## Обмеження моделі

Модель описує сталий шлейф над рівною місцевістю за постійних вітру і класу стійкості. Вона не враховує рельєф, забудову, штиль, хімічні реакції і підйом шлейфу. Середня концентрація залежить від розміру вибраної території. Населення оцінено як площа перевищення, помножена на рівномірну густоту. Грошові коефіцієнти є навчальними припущеннями.

Детальні формули і перелік обмежень: [docs/mathematical_model.md](docs/mathematical_model.md), [docs/assumptions_and_limitations.md](docs/assumptions_and_limitations.md). Постановка проєкту: [docs/project_statement.md](docs/project_statement.md). Джерела даних: [docs/data_sources.md](docs/data_sources.md).
