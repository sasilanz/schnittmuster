# Agents

## Developer
- Use single file HTML structure as requested
- Keep code simple and concise
- Ensure IndexedDB usage is efficient
- No unnecessary comments

## Security
- Review API key handling in settings
- Ensure no sensitive data is logged

## Project Status (2026-03-30)
- **Feature:** Heft-Übersichtsbilder (Modal + Upload in Erfassen + Settings List)
- **Model:** `claude-haiku-4-5` (Anthropic) - Use this for image extraction.
- **Bug:** API-Key muss korrekt in Einstellungen gespeichert werden (geschieht via IndexedDB).
- **Next Step:** Bild-Extraktion testen mit aktuellem Modell.
- **Limitation:** Images must be < 5MB (Anthropic limit). Added validation check.
