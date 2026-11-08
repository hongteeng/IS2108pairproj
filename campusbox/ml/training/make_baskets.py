import csv
import random
from pathlib import Path


MEALS = [
    "Chicken Rice Box",
    "Teriyaki Salmon Bowl",
    "Tofu Veggie Stir Fry",
    "Beef Burrito Bowl",
    "Egg Fried Rice Set",
    "Protein Pasta",
    "Honey Soy Chicken Bowl",
    "Laksa Noodle Bowl",
    "Mushroom Barley Risotto",
    "Tuna Mayo Onigiri Set",
    "Satay Chicken Wrap",
    "Vegan Chickpea Curry",
    "Baked Fish and Sweet Potato",
    "Pork Bulgogi Rice Bowl",
    "Greek Chicken Salad",
    "Soba Veggie Noodles",
    "Egg Mayo Sandwich Set",
    "Mee Goreng Protein Style",
    "Salmon Poke Bowl",
    "Turkey Meatball Pasta",
]

PAIRS = [
    ("Chicken Rice Box", "Egg Mayo Sandwich Set"),
    ("Protein Pasta", "Greek Chicken Salad"),
    ("Tofu Veggie Stir Fry", "Vegan Chickpea Curry"),
    ("Teriyaki Salmon Bowl", "Salmon Poke Bowl"),
    ("Laksa Noodle Bowl", "Tuna Mayo Onigiri Set"),
    ("Beef Burrito Bowl", "Turkey Meatball Pasta"),
]


def make_baskets():
    random.seed(42)
    baskets = []

    for _ in range(360):
        pair = random.choice(PAIRS)
        additional_meals = random.sample(
            [meal for meal in MEALS if meal not in pair],
            random.randint(0, 2),
        )
        baskets.append(list(pair) + additional_meals)

    for _ in range(240):
        baskets.append(random.sample(MEALS, random.randint(1, 3)))

    output_path = Path(__file__).parent / "baskets.csv"
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["order_id", "meal_name"])
        for order_id, basket in enumerate(baskets, start=1):
            for meal in basket:
                writer.writerow([order_id, meal])

    print(f"Made {len(baskets)} baskets.")


if __name__ == "__main__":
    make_baskets()