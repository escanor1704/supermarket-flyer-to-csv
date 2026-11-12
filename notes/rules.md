csv file columns
Column	Example	Rule
week	2026-W46	Calendar week of the flyer
store	kaufland	Always lowercase
page	10	Page number in the flyer
brand	Sanella	Empty if none is printed
product_name	Streichfett	As printed
pack_size	400	Number only
unit	g	Only g, kg, ml, l or piece
offer_price_eur	1.49	The big price; always a dot, never a comma
regular_price_eur	1.69	The crossed-out price; empty if none
discount_pct	34	The “-34%”; empty if none
unit_price_eur	3.73	From “(1 kg = 3.73)”
unit_price_basis	kg	kg, l or piece
label	KNÜLLER	Marketing label: KNÜLLER, AKTION, empty
condition		“nur mit App”, “ab Donnerstag”, empty
valid_from	2026-11-09	From “AB MO. 09.11.”
valid_to	2026-11-14	From “BIS SA. 14.11.”

new column:
category	Examples
bakery	bread, rolls, cake
meat_sausage	Kalbshaxe, Salami, Entenkeule (raw)
fish	Thunfischfilet
dairy_cheese	milk, yoghurt, cheese, butter, eggs
fruit_vegetables	apples, tomatoes, potatoes
baking_cooking	sugar, flour, oil, fat, spices, Back-Oblaten
breakfast_spreads	Haferflocken, jam, honey, Nutella
pasta_rice_grains	pasta, rice, lentils
ready_meals	Käse-Makkaroni Auflauf, portions from the counter
frozen	frozen pizza, ice cream
snacks_sweets	chips, chocolate
drinks	water, juice, coffee
alcohol	beer, wine
household	Backpapier, cleaning products
personal_care	shampoo, toothpaste
other	anything that doesn’t fit; write why in notes
