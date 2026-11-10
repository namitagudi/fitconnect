"""Starter food table (per 100 g). APPROXIMATE typical values for common foods, compiled for this app - not lab data.
For stronger accuracy swap in USDA FoodData Central or India's IFCT tables."""
from .db import get_db

FOODS = [  # name, kcal, protein, carbs, fat, serving label, serving grams
("Idli", 145, 5, 30, 1, "1 piece", 40), ("Plain dosa", 168, 4, 25, 6, "1 dosa", 80), ("Uttapam", 180, 5, 28, 5, "1 piece", 100),
("Medu vada", 300, 9, 30, 15, "1 piece", 40), ("Chapati / roti", 297, 10, 50, 7.5, "1 roti", 35), ("Paratha", 326, 7, 45, 13, "1 piece", 60),
("Aloo paratha", 260, 6, 38, 10, "1 piece", 90), ("Puri", 350, 7, 45, 16, "1 piece", 25), ("Cooked white rice", 130, 2.7, 28, .3, "1 cup", 158),
("Cooked brown rice", 112, 2.3, 24, .8, "1 cup", 195), ("Khichdi", 120, 4, 20, 2.5, "1 bowl", 200), ("Dal (cooked)", 116, 9, 20, .4, "1 small bowl", 150),
("Rajma curry", 120, 6, 17, 3, "1 small bowl", 150), ("Chole (chickpea curry)", 150, 7, 20, 5, "1 small bowl", 150), ("Sambar", 50, 2.5, 8, 1, "1 small bowl", 150),
("Rasam", 25, 1, 4, .5, "1 small bowl", 150), ("Chicken curry", 150, 14, 4, 8, "1 small bowl", 150), ("Egg curry", 130, 8, 5, 9, "1 small bowl", 150),
("Mutton curry", 200, 16, 4, 13, "1 small bowl", 150), ("Prawn curry", 110, 12, 4, 5, "1 small bowl", 150), ("Fish, cooked", 150, 22, 0, 6, "1 piece", 100),
("Tandoori chicken", 185, 24, 3, 8, "1 piece", 100), ("Grilled chicken breast", 165, 31, 0, 3.6, "1 breast", 120), ("Boiled egg", 155, 13, 1.1, 11, "1 egg", 50),
("Paneer", 265, 18, 1.2, 20, "1 cube", 20), ("Tofu", 76, 8, 2, 4.8, "100 g", 100), ("Soya chunks (cooked)", 120, 17, 9, .5, "1 bowl", 100),
("Potato sabzi", 110, 2, 15, 5, "1 small bowl", 150), ("Mixed vegetable curry", 90, 2.5, 9, 5, "1 small bowl", 150), ("Salad (mixed vegetables)", 25, 1.2, 4.5, .3, "1 bowl", 100),
("Cucumber", 15, .7, 3.6, .1, "1 cup", 100), ("Poha", 130, 2.5, 25, 2.5, "1 plate", 150), ("Upma", 140, 3, 20, 5, "1 plate", 200),
("Dhokla", 160, 6, 25, 4, "1 piece", 40), ("Chicken biryani", 165, 8, 22, 5, "1 plate", 250), ("Pav bhaji", 150, 4, 20, 6, "1 plate", 250),
("Samosa", 262, 3.5, 24, 17, "1 piece", 60), ("Plain curd / yogurt", 61, 3.5, 4.7, 3.3, "1 small bowl", 100), ("Buttermilk", 35, 1.7, 4.8, 1, "1 glass", 240),
("Lassi (sweet)", 90, 3, 15, 2, "1 glass", 250), ("Milk (whole)", 61, 3.2, 4.8, 3.3, "1 glass", 250), ("Tea with milk and sugar", 45, 1.2, 6.5, 1.5, "1 cup", 150),
("Coconut water", 19, .7, 3.7, .2, "1 glass", 240), ("Banana", 89, 1.1, 23, .3, "1 medium", 118), ("Apple", 52, .3, 14, .2, "1 medium", 182),
("Orange", 47, .9, 12, .1, "1 medium", 131), ("Mango", 60, .8, 15, .4, "1 cup", 165), ("Grapes", 69, .7, 18, .2, "1 cup", 150),
("Watermelon", 30, .6, 8, .2, "1 cup", 150), ("Papaya", 43, .5, 11, .3, "1 cup", 140), ("Guava", 68, 2.6, 14, 1, "1 medium", 100),
("Sweet potato (boiled)", 76, 1.4, 18, .1, "1 medium", 130), ("Almonds", 579, 21, 22, 50, "1 handful", 28), ("Cashews", 553, 18, 30, 44, "1 handful", 28),
("Peanuts (roasted)", 590, 26, 16, 50, "1 handful", 28), ("Peanut butter", 588, 25, 20, 50, "1 tbsp", 16), ("Bread (white)", 265, 9, 49, 3.2, "1 slice", 28),
("Oats (cooked)", 71, 2.5, 12, 1.5, "1 cup", 234), ("Pasta (cooked)", 158, 5.8, 31, .9, "1 cup", 140), ("Pizza (cheese)", 266, 11, 33, 10, "1 slice", 107),
("French fries", 312, 3.4, 41, 15, "1 serving", 117), ("Gulab jamun", 330, 5, 50, 12, "1 piece", 40), ("Kheer", 140, 3.5, 22, 4.5, "1 bowl", 150),
]


def seed_foods():
    db = get_db()
    for f in FOODS:
        db.execute("INSERT OR IGNORE INTO foods(name,kcal,protein,carbs,fat,serving_label,serving_g) VALUES(?,?,?,?,?,?,?)", f)
    db.commit()
