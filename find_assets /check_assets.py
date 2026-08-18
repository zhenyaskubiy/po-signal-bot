from pocketoptionapi_async import ASSETS

# Отримуємо всі ключі як звичайний список
all_assets = list(ASSETS.keys())

print(f"Всього доступних активів у бібліотеці: {len(all_assets)}\n")

# Виведемо перші 50 активів безпосередньо зі списку
print("Приклади перших 50 активів:")
for symbol in all_assets[:50]:
    print(f"  - {symbol}")

# Можна одразу зберегти повний список у текстовий файл, щоб зручно переглянути
with open("available_assets.txt", "w", encoding="utf-8") as f:
    for symbol in sorted(all_assets):
        f.write(f"- {symbol}\n")

print("\n💾 Повний список усіх активів успішно збережено у файл 'available_assets.txt'!")