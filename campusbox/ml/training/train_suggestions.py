import csv
import inspect
import joblib
from pathlib import Path

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder


def main():
    training_dir = Path(__file__).parent
    baskets_path = training_dir / "baskets.csv"
    baskets_by_order = {}
    with baskets_path.open(newline="", encoding="utf-8") as baskets_file:
        for row in csv.DictReader(baskets_file):
            baskets_by_order.setdefault(row["order_id"], []).append(row["meal_name"])

    transactions = list(baskets_by_order.values())
    encoder = TransactionEncoder()
    encoded_transactions = encoder.fit(transactions).transform(transactions)
    encoded_data = pd.DataFrame(encoded_transactions, columns=encoder.columns_)

    frequent_itemsets = apriori(
        encoded_data,
        min_support=0.03,
        use_colnames=True,
    )
    rules_kwargs = {
        "metric": "lift",
        "min_threshold": 1.2,
    }
    if "num_itemsets" in inspect.signature(association_rules).parameters:
        rules_kwargs["num_itemsets"] = len(transactions)
    rules = association_rules(frequent_itemsets, **rules_kwargs)
    rules = rules[
        (rules["antecedents"].map(len) == 1)
        & (rules["consequents"].map(len) == 1)
    ].sort_values(["lift", "confidence"], ascending=False)

    suggestions = {}
    for _, rule in rules.iterrows():
        meal = next(iter(rule["antecedents"]))
        suggested_meal = next(iter(rule["consequents"]))
        suggestions.setdefault(meal, [])
        if suggested_meal not in suggestions[meal] and len(suggestions[meal]) < 3:
            suggestions[meal].append(suggested_meal)

    output_path = training_dir.parent / "trained_models" / "meal_suggestions.joblib"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"suggestions": suggestions}, output_path)

    print("Top 10 rules:")
    for _, rule in rules.head(10).iterrows():
        antecedent = next(iter(rule["antecedents"]))
        consequent = next(iter(rule["consequents"]))
        print(
            f"{antecedent} -> {consequent} "
            f"(support={rule['support']:.2f}, "
            f"confidence={rule['confidence']:.2f}, "
            f"lift={rule['lift']:.2f})"
        )
    print(f"Meals with suggestions: {len(suggestions)}")


if __name__ == "__main__":
    main()