"""Generate Kaari catalog JSON from extracted PDF data."""
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CATALOG = [
    # ─── NEO COLLECTION ───
    {"model": "DEW", "coll": "Neo", "desc": "Conical FRP planter.", "variants": [
        ("21", 4200, 8.5, 6.5, 21, ["Light Ivory"], "Matte", 7),
        ("28", 7300, 11, 8.5, 28, ["Light Ivory"], "Orange Peel", 7),
        ("33", 9900, 13.5, 10, 33, ["Light Ivory"], "Matte", 7),
        ("40", 14600, 16, 12, 40, ["Pearl Beige"], "Matte", 7),
    ]},
    {"model": "NOVA", "coll": "Neo", "desc": "Tapered oval FRP planter.", "variants": [
        ("10", 4200, 7.5, 8, 10, ["Pearl Beige"], "Matte", 9),
        ("15", 6300, 10, 9.25, 15, ["Pearl Beige"], "Orange Peel", 9),
        ("22", 9400, 13, 11, 22.5, ["Light Ivory"], "Orange Peel", 9),
    ]},
    {"model": "HAVEN", "coll": "Neo", "desc": "Rectangular FRP planter.", "variants": [
        ("9", 3100, 10, 12, 9, ["Traffic Grey"], "Matte", 11),
        ("12", 5200, 14, 17, 12.5, ["Traffic Grey"], "Matte", 11),
        ("16", 9400, 18.5, 22, 16, ["Traffic Grey"], "Matte", 11),
    ]},
    {"model": "ASH", "coll": "Neo", "desc": "Tapered FRP planter.", "variants": [
        ("7", 2600, 7, 6, 7, ["Jet Black"], "Matte", 13),
        ("10", 4200, 10, 9, 10, ["Stone Grey"], "Matte", 13),
        ("13", 6300, 13.7, 12, 13.5, ["Pure White"], "Matte", 13),
        ("17", 10500, 18.5, 16, 17.5, ["Stone Grey"], "Matte", 13),
    ]},
    {"model": "DIAMOND", "coll": "Neo", "desc": "Diamond-shaped FRP planter.", "variants": [
        ("8", 3100, 9, 6, 8.5, ["Stone Grey"], "Matte", 15),
        ("12", 6300, 13, 9, 12, ["Stone Grey"], "Matte", 15),
        ("16", 8400, 17.5, 12, 16, ["Stone Grey"], "Matte", 15),
    ]},
    {"model": "PINE", "coll": "Neo", "desc": "Conical FRP planter.", "variants": [
        ("12", 3100, 11.5, 6.5, 12, ["Pale Green"], "Matte", 17),
        ("15", 5200, 13.5, 8, 15.5, ["Pale Green"], "Matte", 17),
        ("19", 9400, 17.5, 10, 19.5, ["Pale Green"], "Matte", 17),
    ]},
    {"model": "MOAI", "coll": "Neo", "desc": "Large sculptural FRP planter.", "variants": [
        ("32", 17800, 14.5, 14.5, 32, ["Stone Grey"], "Orange Peel", 21),
        ("39", 23000, 18, 18.5, 39.5, ["Stone Grey"], "Orange Peel", 21),
    ]},
    {"model": "GAZE", "coll": "Neo", "desc": "Elegant tapered FRP planter.", "variants": [
        ("28", 9400, 12, 9, 28.5, ["Signal Black"], "Matte", 23),
        ("36", 13600, 15, 9.5, 36, ["Pure White"], "Matte", 23),
        ("44", 16700, 15, 10, 44, ["Signal Black"], "Matte", 23),
    ]},
    {"model": "KIMI", "coll": "Neo", "desc": "Cylindrical concrete-texture FRP planter.", "variants": [
        ("17", 5200, 10, 10, 17, ["Pure White"], "Concrete", 25),
        ("24", 8400, 12, 12, 24, ["Grey Beige"], "Concrete", 25),
        ("30", 10500, 14, 14, 30, ["Pure White"], "Concrete", 25),
        ("40", 14600, 16, 16, 40, ["Grey Beige"], "Concrete", 25),
    ]},
    {"model": "AQUA", "coll": "Neo", "desc": "Versatile FRP planter range.", "variants": [
        ("12", 3700, 10, 6.5, 12.5, ["Pearl Beige"], "Matte", 27),
        ("16", 6300, 13.5, 8, 16.5, ["Light Ivory"], "Stone Texture", 27),
        ("20", 10500, 17, 10.5, 20.5, ["Pearl Beige"], "Matte", 27),
        ("24", 14600, 20.5, 12.5, 24.5, ["Light Ivory"], "Matte", 27),
        ("28", 20900, 23.5, 15, 28.5, ["Grey Beige"], "Orange Peel", 27),
        ("32", 24000, 27.5, 17, 32.5, ["Light Ivory"], "Sand", 27),
    ]},
    {"model": "OASIS", "coll": "Neo", "desc": "Tapered FRP planter.", "variants": [
        ("8", 4700, 14, 6.5, 8.5, ["Pure White"], "Sand", 29),
        ("10", 6800, 17.5, 7.5, 10.5, ["Stone Grey"], "Sand & Dotted", 29),
        ("12", 10500, 23, 9, 12, ["Pure White"], "Orange Peel", 29),
        ("14", 13600, 26.5, 10, 14, ["Stone Grey"], "Matte", 29),
        ("16", 18800, 30, 12.5, 16, ["Pure White"], "Matte", 29),
    ]},
    {"model": "CORAL", "coll": "Neo", "desc": "Wide FRP planter.", "variants": [
        ("14", 5200, 9.5, 14, 14, ["Orange Brown"], "Matte", 31),
        ("18", 7300, 11.5, 18, 18, ["Pure White"], "Sand & Dotted", 31),
        ("24", 13100, 15.5, 24, 24, ["Slate Grey"], "Matte", 31),
        ("30", 20900, 19.5, 30, 30, ["Yellow Grey"], "Orange Peel", 31),
    ]},
    {"model": "CANOE", "coll": "Neo", "desc": "Elongated FRP planter.", "variants": [
        ("8", 5200, 29, 10, 8.5, ["Pearl Beige"], "Matte", 33),
        ("11", 7300, 33, 13, 11, ["Oyster White"], "Matte", 33),
        ("13", 10500, 39, 16, 13.5, ["Pearl Beige"], "Matte", 33),
    ]},
    {"model": "MARVEL", "coll": "Neo", "desc": "Statement FRP planter.", "variants": [
        ("18", 13600, 17, 21, 18, ["Slate Grey"], "Orange Peel", 35),
        ("30", 12500, 12, 12, 30, ["Oyster White"], "Sand & Dotted", 35),
        ("36", 14600, 14, 13, 36, ["Slate Grey"], "Orange Peel", 35),
        ("44", 18800, 17, 14.5, 44, ["Oyster White"], "Sand & Dotted", 35),
    ]},
    {"model": "POP", "coll": "Neo", "desc": "Compact FRP planter.", "variants": [
        ("11", 3100, 10, 11, 11, ["Grey Beige"], "Orange Peel & Dotted", 37),
        ("15", 5200, 13, 14, 15, ["Black Grey"], "Orange Peel", 37),
        ("20", 6300, 14, 15, 20, ["Light Ivory"], "Matte", 37),
        ("25", 8400, 14.5, 16, 25, ["Light Ivory"], "Orange Peel", 37),
    ]},
    {"model": "PEARL", "coll": "Neo", "desc": "Elegant round FRP planter.", "variants": [
        ("14", 4700, 11, 10.25, 14.5, ["Olive Green"], "Matte", 39),
        ("24", 8400, 13, 16, 24.5, ["Pure White"], "Orange Peel", 39),
        ("30", 12500, 16, 14.5, 30, ["Olive Green"], "Matte", 39),
    ]},
    {"model": "SCALE", "coll": "Neo", "desc": "Textured FRP planter.", "variants": [
        ("18", 4200, 9.5, 6, 18, ["Pure White"], "Matte", 41),
        ("23", 6300, 12, 7.5, 23, ["Jet Black"], "Matte", 41),
        ("28", 8900, 15, 9, 28.5, ["Pure White"], "Matte", 41),
    ]},
    {"model": "LUSH", "coll": "Neo", "desc": "Tall elegant FRP planter.", "variants": [
        ("14", 4200, 12.5, 7, 14, ["Black Grey"], "Matte", 43),
        ("17", 7300, 16, 9, 17, ["Black Grey"], "Matte", 43),
        ("21", 10500, 19, 10.5, 21, ["Black Grey"], "Matte", 43),
    ]},
    {"model": "VERDURE", "coll": "Neo", "desc": "Large FRP planter.", "variants": [
        ("16", 5700, 10.5, 10, 16, ["Stone Grey"], "Matte", 45),
        ("25", 12500, 17, 16, 25.5, ["Stone Grey"], "Matte", 45),
    ]},
    {"model": "PEAR", "coll": "Neo", "desc": "Pear-shaped FRP planter.", "variants": [
        ("15", 5200, 10.5, 14, 15, ["Pure White"], "Matte", 47),
        ("20", 6300, 11, 15, 20, ["Pure White"], "Matte", 47),
        ("26", 8400, 12, 16, 26, ["Black Grey"], "Sand & Dotted", 47),
    ]},
    # ─── HERITAGE COLLECTION ───
    {"model": "BUENO", "coll": "Heritage", "desc": "Classic FRP planter.", "variants": [
        ("14", 6300, 12, 7, 14, ["Grey Beige"], "Matte", 19),
        ("18", 8400, 15, 11, 18, ["Grey Beige"], "Orange Peel", 19),
        ("29", 12500, 14, 8.5, 29, ["Oyster White"], "Stone Texture", 19),
    ]},
    {"model": "URN", "coll": "Heritage", "desc": "Heritage urn-shaped FRP planter.", "variants": [
        ("17", 13600, 18, 6, 17.5, ["Grey Beige"], "Stone Texture", 49),
        ("37", 17800, 14, 6, 39, ["Grey Beige"], "Stone Texture", 49),
        ("52", 41800, 23, 8.5, 52, ["Grey Beige"], "Stone Texture", 49),
        ("67", 104500, 34.5, 15, 67, ["Grey Beige"], "Stone Texture", 49),
    ]},
    {"model": "AYU", "coll": "Heritage", "desc": "Heritage FRP planter with Distressed Ink finish.", "variants": [
        ("18", 12500, 19, 13, 18, ["Traffic Grey"], "Distressed Ink", 51),
        ("27", 21900, 22, 17, 27.5, ["Traffic Grey"], "Distressed Ink", 51),
        ("47", 41800, 26, 15, 47, ["Traffic Grey"], "Distressed Ink", 51),
    ]},
    {"model": "AURA", "coll": "Heritage", "desc": "Heritage oval FRP planter with Sand Texture base.", "variants": [
        ("24", 13600, 19, 12, 24, ["Pearl Gold"], "Distressed Ink", 53),
        ("40", 31400, 20, 12, 40, ["Pearl Gold"], "Distressed Ink", 53),
        ("56", 46000, 27, 17, 56, ["Pearl Gold"], "Distressed Ink", 53),
    ]},
    {"model": "MANDALA", "coll": "Heritage", "desc": "Heritage oval FRP planter.", "variants": [
        ("18", 8400, 17, 8, 18, ["Black Grey"], "Matte", 55),
        ("32", 19900, 23, 13, 32, ["Black Grey"], "Matte", 55),
        ("47", 37600, 26, 17, 47, ["Black Grey"], "Matte", 55),
    ]},
    {"model": "OLIVE", "coll": "Heritage", "desc": "Small FRP planter.", "variants": [
        ("8", 2600, 4, 4, 8, ["Grey White"], "Matte", 57),
        ("11", 3100, 9, 6, 11.5, ["Grey White"], "Matte", 57),
        ("15", 6300, 12, 8, 15.5, ["Grey White"], "Matte", 57),
    ]},
    {"model": "BELLA", "coll": "Heritage", "desc": "Heritage FRP planter.", "variants": [
        ("12", 4200, 13.5, 9, 12.5, ["Oyster White"], "Matte", 59),
        ("18", 6300, 18, 11, 18, ["Pure White"], "Matte", 59),
        ("21", 8400, 22, 13, 21, ["Oyster White"], "Sand", 59),
    ]},
    {"model": "ASPEN", "coll": "Heritage", "desc": "Concrete-texture FRP planter.", "variants": [
        ("18", 3700, 8, 4.5, 18, ["Traffic Grey"], "Concrete", 61),
        ("24", 5200, 10.5, 6, 24, ["Traffic Grey"], "Concrete", 61),
        ("30", 6800, 12, 6.5, 30.5, ["Traffic Grey"], "Concrete", 61),
    ]},
    {"model": "BIRCH", "coll": "Heritage", "desc": "Cylindrical FRP planter (hollow body).", "variants": [
        ("10", 4700, 10, 7, 11.5, ["Black Grey"], "Matte", 63),
        ("20", 5700, 10, 7, 20, ["Oyster White"], "Orange Peel", 63),
        ("30", 7300, 10, 7, 30, ["Black Grey"], "Matte", 63),
    ]},
    {"model": "BIRCH-FB", "coll": "Heritage", "desc": "Cylindrical FRP planter (full body).", "variants": [
        ("32", 8400, 13, 13, 32, ["Grey Beige"], "Concrete", 65),
        ("40", 12500, 13, 13, 40, ["Grey Beige"], "Concrete", 65),
    ]},
    {"model": "MEADOW", "coll": "Heritage", "desc": "Organic-shaped FRP planter.", "variants": [
        ("7", 2500, 12, 7, 7, ["Pearl Beige"], "Orange Peel", 67),
        ("8", 4200, 10, 10, 8, ["Pearl Beige"], "Matte", 67),
        ("11", 7300, 20, 12, 11, ["Traffic Grey"], "Orange Peel", 67),
    ]},
    {"model": "COVE", "coll": "Heritage", "desc": "Rounded FRP planter.", "variants": [
        ("12", 4200, 11, 9, 12.5, ["Slate Grey"], "Matte", 69),
        ("20", 7300, 17, 10, 20, ["Pure White"], "Orange Peel", 69),
        ("25", 12500, 20.5, 11, 25, ["Slate Grey"], "Matte", 69),
    ]},
    {"model": "SNOWDROP-FB", "coll": "Heritage", "desc": "FRP planter (full body).", "variants": [
        ("27", 10500, 14, 10, 27.5, ["Orange Brown"], "Matte", 71),
        ("36", 13600, 15, 10.5, 36, ["Pure White"], "Orange Peel", 71),
    ]},
    {"model": "SNOWDROP", "coll": "Heritage", "desc": "FRP planter (hollow body).", "variants": [
        ("11", 3100, 10, 4, 11, ["Grey White"], "Matte", 73),
        ("16", 4200, 12, 4.75, 16, ["Grey White"], "Orange Peel", 73),
        ("22", 6800, 14, 5.75, 22, ["Black Grey"], "Matte", 73),
        ("30", 11500, 16, 6.5, 30, ["Orange Brown"], "Sand & Dotted", 73),
    ]},
    {"model": "PRISTINE", "coll": "Heritage", "desc": "Elegant tapered FRP planter.", "variants": [
        ("12", 4600, 14, 5, 12, ["Papyrus White"], "Matte", 75),
        ("16", 8400, 19, 7, 16, ["Slate Grey"], "Matte", 75),
        ("19", 10500, 22, 7.5, 19, ["Slate Grey"], "Orange Peel", 75),
        ("23", 15700, 27, 10, 23, ["Papyrus White"], "Sand & Dotted", 75),
        ("28", 24000, 33, 12, 28, ["Slate Grey"], "Orange Peel", 75),
        ("32", 33400, 38, 13.5, 32, ["Black Grey"], "Matte", 75),
    ]},
    {"model": "ORBIT", "coll": "Heritage", "desc": "Orb-shaped FRP planter.", "variants": [
        ("10", 4200, 14, 5, 10, ["Olive Green"], "Orange Peel", 77),
        ("14", 7800, 19.5, 7, 14, ["Pearl Beige"], "Sand", 77),
        ("18", 10500, 25, 8.5, 18, ["Light Ivory"], "Sand & Dotted", 77),
        ("22", 16200, 30.5, 10, 22, ["Pearl Beige"], "Matte", 77),
        ("26", 25100, 36, 12, 26, ["Light Ivory"], "Matte", 77),
    ]},
    {"model": "ARLO", "coll": "Heritage", "desc": "Versatile tapered FRP planter.", "variants": [
        ("10", 3100, 10, 5.5, 10, ["Ivory"], "Matte", 79),
        ("12", 3600, 12, 6.5, 12, ["Pearl Gold"], "Matte", 79),
        ("15", 5200, 15, 8.5, 15, ["Grey Beige"], "Matte", 79),
        ("18", 7300, 18, 10, 18, ["Pure White"], "Sand & Dotted", 79),
        ("24A", 14600, 24, 13, 24, ["Olive Green"], "Matte", 79),
        ("24B", 11500, 20, 17, 24, ["Slate Grey"], "Matte", 79),
        ("30", 23000, 30, 17, 30, ["Pure White"], "Orange Peel", 79),
        ("36", 35500, 36, 20, 36, ["Yellow Grey"], "Matte", 79),
        ("40", 36600, 30, 20, 40, ["Grey White"], "Sand", 79),
    ]},
    {"model": "BLUSH", "coll": "Heritage", "desc": "Graceful tapered FRP planter.", "variants": [
        ("8", 2100, 7, 4.5, 8, ["Traffic Grey"], "Matte", 81),
        ("12", 3100, 10, 6.5, 12.5, ["Grey Beige"], "Matte", 81),
        ("15", 4200, 11, 7, 15, ["Slate Grey"], "Matte", 81),
        ("18", 8400, 15, 11, 18, ["Yellow Grey"], "Sand & Dotted", 81),
        ("24", 11500, 20, 15, 24, ["Grey Beige"], "Matte", 81),
        ("34", 24000, 27.5, 16, 34, ["Olive Green"], "Matte", 81),
    ]},
    {"model": "BLOSSOM", "coll": "Heritage", "desc": "Elegant FRP planter.", "variants": [
        ("10", 2600, 9, 4.5, 10, ["Pure White"], "Matte", 83),
        ("14", 4200, 12, 6.5, 14, ["Pale Green"], "Matte", 83),
        ("18", 5700, 16, 8.5, 18, ["Slate Grey"], "Sand & Dotted", 83),
        ("23", 9400, 20, 10.5, 23, ["Yellow Grey"], "Matte", 83),
        ("28", 13600, 24.5, 12.5, 28, ["Olive Green"], "Orange Peel", 83),
    ]},
    {"model": "KAIA", "coll": "Heritage", "desc": "Tall tapered FRP planter.", "variants": [
        ("20", 4200, 10, 6, 20, ["Slate Grey"], "Matte", 85),
        ("27", 7300, 13.5, 8, 27, ["Black Grey"], "Orange Peel", 85),
        ("34", 12500, 17, 10, 34, ["Slate Grey"], "Sand & Dotted", 85),
        ("42", 19900, 21, 12.5, 42, ["Black Grey"], "Orange Peel", 85),
    ]},
    {"model": "PYRAMID", "coll": "Heritage", "desc": "Pyramid-shaped FRP planter.", "variants": [
        ("18", 3700, 9.5, 6, 18, ["Pearl Beige"], "Matte", 87),
        ("24", 6300, 12.5, 7, 24.5, ["Ivory"], "Orange Peel", 87),
        ("31", 10500, 16.5, 10, 31, ["Grey Beige"], "Matte", 87),
        ("40", 16700, 21.5, 13, 40, ["Ivory"], "Orange Peel", 87),
    ]},
    # ─── LINEA COLLECTION ───
    {"model": "EVEREST", "coll": "Linea", "desc": "Mountain-inspired FRP planter.", "variants": [
        ("16", 4200, 10.5, 7.5, 16, ["Beige"], "Matte", 89),
        ("21", 7300, 14.5, 9.5, 21, ["Signal White"], "Matte", 89),
        ("27", 11000, 18, 13, 27.5, ["Beige"], "Matte", 89),
    ]},
    {"model": "FUJI", "coll": "Linea", "desc": "Elegant FRP planter.", "variants": [
        ("12", 4200, 13, 8, 12, ["Traffic Grey"], "Matte", 91),
        ("16", 6800, 17, 10, 16, ["Traffic Grey"], "Matte", 91),
        ("19", 9400, 21, 12, 19, ["Traffic Grey"], "Matte", 91),
    ]},
    {"model": "ATLAS", "coll": "Linea", "desc": "Sturdy FRP planter.", "variants": [
        ("13", 5200, 9.5, 10, 13, ["Grey Beige"], "Matte", 93),
        ("16", 7300, 15, 11, 16, ["Traffic Grey"], "Matte", 93),
        ("19", 6800, 9.5, 10, 19, ["Grey Beige"], "Matte", 93),
        ("24", 8400, 12.5, 12.5, 24, ["Traffic Grey"], "Matte", 93),
    ]},
    {"model": "VICTORIA", "coll": "Linea", "desc": "Square FRP planter.", "variants": [
        ("9", 3100, 9.5, 10, 9.5, ["Ivory"], "Matte", 95),
        ("12", 4200, 12.5, 13, 12.5, ["Ivory"], "Matte", 95),
        ("16", 6900, 16, 16, 16, ["Ivory"], "Matte", 95),
        ("19", 9400, 19, 19, 19, ["Ivory"], "Matte", 95),
    ]},
    {"model": "TITLIS", "coll": "Linea", "desc": "Cylindrical FRP planter.", "variants": [
        ("8", 2600, 8.5, 8, 8, ["Black Grey"], "Matte", 97),
        ("12", 5200, 13, 12, 12, ["Black Grey"], "Matte", 97),
        ("15", 9400, 17.5, 16.5, 15, ["Black Grey"], "Matte", 97),
    ]},
    {"model": "ROSA", "coll": "Linea", "desc": "Cylindrical FRP planter.", "variants": [
        ("9", 3100, 10, 10, 9.5, ["Grey White"], "Matte", 99),
        ("12", 5200, 13, 13, 12, ["Grey White"], "Matte", 99),
        ("16", 8400, 16, 16, 16, ["Grey White"], "Matte", 99),
        ("18", 10500, 20, 20, 18.5, ["Grey White"], "Matte", 99),
    ]},
    {"model": "MOIRE", "coll": "Linea", "desc": "Two-tone FRP planter with glossy rim.", "variants": [
        ("12", 5200, 12, 10, 12, ["Stone Grey"], "Rim - Glossy, Body - Matte", 101),
        ("16", 8400, 16, 14, 16, ["Stone Grey"], "Rim - Glossy, Body - Matte", 101),
        ("20", 12500, 20, 18, 20, ["Stone Grey"], "Rim - Glossy, Body - Matte", 101),
    ]},
    {"model": "TAI", "coll": "Linea", "desc": "Tapered cylindrical FRP planter.", "variants": [
        ("13", 5700, 14, 9, 13, ["Black Grey"], "Matte", 103),
        ("16", 7300, 16, 11, 16, ["Black Grey"], "Matte", 103),
        ("19", 9400, 20, 13, 19, ["Black Grey"], "Matte", 103),
    ]},
    {"model": "ALPS", "coll": "Linea", "desc": "Tapered FRP planter.", "variants": [
        ("9", 3100, 10, 6, 9, ["Yellow Grey"], "Matte", 105),
        ("12", 5200, 13, 8, 12, ["Oyster White"], "Matte", 105),
        ("16", 9400, 18, 11, 16, ["Yellow Grey"], "Matte", 105),
    ]},
    {"model": "BLANC", "coll": "Linea", "desc": "Tapered cylindrical FRP planter.", "variants": [
        ("10", 2600, 7.5, 4.5, 10, ["Stone Grey"], "Matte", 107),
        ("15", 4700, 11, 7.5, 15, ["Stone Grey"], "Matte", 107),
        ("20", 8400, 15, 12, 20, ["Stone Grey"], "Matte", 107),
    ]},
    {"model": "FLUTE", "coll": "Linea", "desc": "Glossy FRP planter with golden rim.", "variants": [
        ("12", 7300, 20, 17, 12, ["Jet Black"], "Glossy", 109),
        ("15", 4700, 11, 8, 15, ["Jet Black"], "Glossy", 109),
        ("24", 12500, 20, 16.5, 24, ["Jet Black"], "Glossy", 109),
        ("33", 16700, 18, 12, 33, ["Jet Black"], "Glossy", 109),
    ]},
    {"model": "FLUTO", "coll": "Linea", "desc": "Cylindrical FRP planter.", "variants": [
        ("9", 6300, 12.5, 12.5, 9, ["Black Grey"], "Matte", 111),
        ("13", 8400, 14.5, 14.5, 13.5, ["Papyrus White"], "Matte", 111),
        ("19", 12500, 16.5, 16.5, 19, ["Black Grey"], "Matte", 111),
        ("25", 20900, 19, 19, 25, ["Papyrus White"], "Matte", 111),
    ]},
    {"model": "RECTANGLE", "coll": "Linea", "desc": "Rectangular FRP planter.", "variants": [
        ("240606", 4250, None, None, None, ["Pure White"], "Matte", 113, 24, 6, 6),
        ("390606", 6050, None, None, None, ["Pure White"], "Matte", 113, 39, 6, 6),
        ("121007", 3100, None, None, None, ["Pure White"], "Matte", 113, 12, 10, 7),
        ("460608", 8250, None, None, None, ["Pure White"], "Matte", 113, 46, 6, 8),
        ("100810", 3350, None, None, None, ["Pure White"], "Matte", 113, 10, 8, 10),
        ("120810", 3800, None, None, None, ["Pure White"], "Matte", 113, 12, 8, 10),
        ("240810", 6100, None, None, None, ["Pure White"], "Matte", 113, 24, 8, 10),
        ("360810", 8400, None, None, None, ["Pure White"], "Matte", 113, 36, 8, 10),
        ("241210", 7300, None, None, None, ["Pure White"], "Matte", 114, 24, 12, 10),
        ("240812", 6300, None, None, None, ["Pure White"], "Matte", 114, 24, 8, 12),
        ("241012", 6700, None, None, None, ["Pure White"], "Matte", 114, 24, 10, 12),
        ("241212", 7300, None, None, None, ["Pure White"], "Matte", 114, 24, 12, 12),
        ("361212", 11500, None, None, None, ["Pure White"], "Matte", 114, 36, 12, 12),
        ("481212", 14600, None, None, None, ["Pure White"], "Matte", 114, 48, 12, 12),
        ("361512", 12400, None, None, None, ["Pure White"], "Matte", 114, 36, 15, 12),
        ("481215", 14950, None, None, None, ["Pure White"], "Matte", 114, 48, 12, 15),
        ("691416", 20050, None, None, None, ["Pure White"], "Matte", 114, 69, 14, 16),
        ("721416", 21700, None, None, None, ["Pure White"], "Matte", 115, 72, 14, 16),
        ("241218", 10350, None, None, None, ["Pure White"], "Matte", 115, 24, 12, 18),
        ("361518", 13050, None, None, None, ["Pure White"], "Matte", 115, 36, 15, 18),
        ("241818", 13450, None, None, None, ["Pure White"], "Matte", 115, 24, 18, 18),
        ("301818", 13050, None, None, None, ["Pure White"], "Matte", 115, 30, 18, 18),
        ("361818", 14950, None, None, None, ["Jet Black"], "Matte", 115, 36, 18, 18),
        ("402020", 20900, None, None, None, ["Pure White"], "Matte", 115, 40, 20, 18),
        ("362022", 21900, None, None, None, ["Slate Grey"], "Matte", 115, 36, 20, 22),
        ("781424", 35500, None, None, None, ["Pure White"], "Matte", 115, 78, 14, 24),
        ("362424", 26100, None, None, None, ["Jet Black"], "Matte", 116, 36, 24, 24),
        ("361036", 23000, None, None, None, ["Jet Black"], "Matte", 116, 36, 10, 36),
        ("474736", 62700, None, None, None, ["Slate Grey"], "Matte", 116, 47, 47, 36),
        ("241040", 17800, None, None, None, ["Pure White"], "Matte", 116, 24, 10, 40),
    ]},
    {"model": "CUBE", "coll": "Linea", "desc": "Cube FRP planter.", "variants": [
        ("12", 4200, None, None, None, ["Pure White"], "Orange Peel", 118, 12, 12, 12),
        ("14", 6300, None, None, None, ["Pure White"], "Matte", 118, 14, 14, 14),
        ("18", 10500, None, None, None, ["Slate Grey"], "Matte", 118, 18, 18, 18),
        ("20", 13600, None, None, None, ["Pure White"], "Matte", 118, 20, 20, 20),
        ("24", 20900, None, None, None, ["Jet Black"], "Matte", 118, 24, 24, 24),
        ("30", 30300, None, None, None, ["Pure White"], "Sand & Dotted", 118, 30, 30, 30),
        ("36", 41800, None, None, None, ["Traffic Grey"], "Matte", 118, 36, 36, 36),
    ]},
]

products = []
for entry in CATALOG:
    model = entry["model"]
    coll = entry["coll"]
    desc = entry["desc"]
    variants = []
    for v in entry["variants"]:
        vid = f"{model}-{v[0]}"
        pv = {
            "variant_id": vid,
            "size_label": v[0],
            "listed_price": v[1],
            "currency": "INR",
            "dimensions_unit": "inch",
            "colours": v[5],
            "finish": v[6],
            "texture": v[6],
            "catalog_page": v[7],
        }
        if len(v) > 10 and v[8] is not None:
            pv["length"] = v[8]
            pv["width"] = v[9]
            pv["height"] = v[10]
        else:
            if v[2] is not None:
                pv["upper_diameter"] = v[2]
            if v[3] is not None:
                pv["lower_diameter"] = v[3]
            if v[4] is not None:
                pv["height"] = v[4]
        variants.append(pv)
    products.append({
        "product_id": f"KP-{model}",
        "tenant_id": "kaari-planters",
        "model_name": model,
        "collection": coll,
        "description": desc,
        "variants": variants,
        "catalog_version": "2026",
    })

print(json.dumps(products, indent=2, ensure_ascii=False))
