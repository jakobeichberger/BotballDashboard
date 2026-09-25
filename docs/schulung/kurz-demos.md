# Kurz-Demos

Zwei kurze Vorführungen mit einem beliebigen KI-Chat. Demo 1 ist im Hauptteil (Block „Bessere Ergebnisse“), Demo 2 ist die Reserve im Anhang.

## Demo 1 – Vage gegen präzise (3 Minuten)

Beide Prompts nacheinander in einen **neuen** Chat eingeben.

**Prompt A:**

```text
Wie rechnet man den Seeding-Score?
```

**Prompt B:**

```text
Wir sind ein Botball-Team. Laut Game Review 2026 zählt der Schnitt der besten 2 von 3
Seeding-Runden, Werte unter 0 zählen als 0. Unsere Runden: 120, −10, 85.
Rechne unseren Seed Score und erkläre jeden Schritt in höchstens 3 Sätzen.
```

**Richtige Lösung:** −10 zählt als 0. Die besten zwei Runden sind 120 und 85, der Schnitt ist **102,5**.

**Frage an die Klasse:** Welche Antwort könnt ihr selbst nachprüfen? Was musste Prompt A sich ausdenken? Prompt A liefert meist eine allgemeine Erklärung, oft mit anderen Regeln oder erfundenen Details.

## Demo 2 – KI als Code-Reviewer (4 Minuten)

Der Fehler aus dem Fallbeispiel „Wenn der Test lügt“, verkleinert:

```python
def paper_score(final_score):
    # final_score: 0 bis 1
    return final_score / 100
```

**Mit Kontext:**

```text
Diese Funktion stammt aus unserem Turnier-Dashboard. final_score liegt in der Datenbank
zwischen 0 und 1, die Gesamtwertung erwartet 0 bis 1. Finde den Fehler, erkläre die
Auswirkung und schreibe einen Test, der ihn zeigt.
```

**Danach ohne Kontext** in einem neuen Chat:

```text
Prüfe diese Funktion.
```

**Erwartung:**

- Mit Kontext findet die KI fast sicher die doppelte Umrechnung. Sie schlägt einen Test mit einem realistischen Wert wie 0,8 vor, der 0,8 erwartet und nicht 0,008.
- Ohne Kontext hält sie den Code oft für korrekt.

**Lehre:** Kontext entscheidet, ob ein Review etwas findet.
