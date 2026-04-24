import typer
import httpx
import json

app = typer.Typer()
API_URL = "http://127.0.0.1:8000/api"

@app.command()
def update(title: str = typer.Option(None, "--title", "-t", help="Новое название стрима"),
           game: str = typer.Option(None, "--game", "-g", help="Новая категория"),
           platform: str = typer.Option(None, "--platform", "-p", help="Конкретная платформа")):
    """Обновить информацию о стриме."""
    try:
        resp = httpx.post(f"{API_URL}/update", json={"title": title, "game": game, "platform": platform})
        typer.secho("✅ Успех:", fg=typer.colors.GREEN)
        typer.echo(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except httpx.ConnectError:
        typer.secho("❌ Ошибка: StreamTail не запущен (API недоступен).", fg=typer.colors.RED)

@app.command()
def status():
    """Получить статус платформ."""
    try:
        resp = httpx.get(f"{API_URL}/status")
        data = resp.json()
        for plat, info in data.items():
            status_txt = "В ЭФИРЕ 🟢" if info['is_live'] else "ОФФЛАЙН 🔴"
            typer.secho(f"\n{plat.upper()} — {status_txt}", fg=typer.colors.CYAN, bold=True)
            typer.echo(f"  Название: {info['title']}")
            typer.echo(f"  Категория: {info['game']}")
            typer.echo(f"  Зрители: {info['viewers']}")
    except httpx.ConnectError:
        typer.secho("❌ Ошибка: StreamTail не запущен.", fg=typer.colors.RED)

if __name__ == "__main__":
    app()
