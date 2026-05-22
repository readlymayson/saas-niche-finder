import { FormEvent, useCallback, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  fetchSimilarNiches,
  fetchTopNiches,
  login,
  register,
  searchNiches,
  type NicheCard,
  type TokenPair,
} from "@/lib/api"

type View = "auth" | "dashboard"

function App() {
  const [view, setView] = useState<View>(
    localStorage.getItem("access_token") ? "dashboard" : "auth",
  )
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [niches, setNiches] = useState<NicheCard[]>([])
  const [similar, setSimilar] = useState<NicheCard[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [searchQ, setSearchQ] = useState("")
  const [loading, setLoading] = useState(false)

  const storeTokens = (tokens: TokenPair) => {
    localStorage.setItem("access_token", tokens.access_token)
    localStorage.setItem("refresh_token", tokens.refresh_token)
    setView("dashboard")
  }

  const onAuth = async (mode: "login" | "register") => {
    setError(null)
    setLoading(true)
    try {
      const tokens =
        mode === "login" ? await login(email, password) : await register(email, password)
      storeTokens(tokens)
      await loadNiches()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка авторизации")
    } finally {
      setLoading(false)
    }
  }

  const loadNiches = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      setNiches(await fetchTopNiches(10))
      setSimilar([])
      setSelectedId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить ниши")
    } finally {
      setLoading(false)
    }
  }, [])

  const onSearch = async () => {
    if (!searchQ.trim()) return
    setError(null)
    setLoading(true)
    try {
      setNiches(await searchNiches(searchQ.trim()))
      setSimilar([])
      setSelectedId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка поиска")
    } finally {
      setLoading(false)
    }
  }

  const openSimilar = async (id: number) => {
    setError(null)
    setLoading(true)
    try {
      setSelectedId(id)
      setSimilar(await fetchSimilarNiches(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить похожие")
    } finally {
      setLoading(false)
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void onAuth("login")
  }

  const logout = () => {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    setView("auth")
    setNiches([])
  }

  if (view === "auth") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
        <div className="max-w-md w-full space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight text-center">SaaS Niche Finder</h1>
          <p className="text-muted-foreground text-center text-sm">
            MVP: дашборд ниш. Free — 5 просмотров карточек в сутки.
          </p>
          <form onSubmit={onSubmit} className="space-y-3">
            <input
              className="w-full border rounded-md px-3 py-2 text-sm"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              className="w-full border rounded-md px-3 py-2 text-sm"
              type="password"
              placeholder="Пароль (мин. 8)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-2">
              <Button type="submit" disabled={loading}>
                Войти
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={loading}
                onClick={() => void onAuth("register")}
              >
                Регистрация
              </Button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-8 max-w-3xl mx-auto space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Дашборд ниш</h1>
          <p className="text-sm text-muted-foreground">Топ по скорингу · API /v1/niches/top</p>
        </div>
        <Button variant="outline" onClick={logout}>
          Выйти
        </Button>
      </header>
      <div className="flex flex-wrap gap-2 items-center">
        <Button onClick={() => void loadNiches()} disabled={loading}>
          {loading ? "Загрузка…" : "Обновить топ"}
        </Button>
        <input
          className="border rounded-md px-3 py-2 text-sm flex-1 min-w-[12rem]"
          placeholder="Поиск по названию…"
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
        />
        <Button variant="outline" disabled={loading} onClick={() => void onSearch()}>
          Найти
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-3">
        {niches.map((n) => (
          <li key={n.id} className="border rounded-lg p-4">
            <div className="font-medium">{n.title}</div>
            <div className="text-sm text-muted-foreground">{n.slug}</div>
            {n.summary && <p className="text-sm mt-2 line-clamp-3">{n.summary}</p>}
            {n.score != null && (
              <p className="text-xs mt-2 text-muted-foreground">Score: {n.score}</p>
            )}
            <Button
              className="mt-2"
              variant="outline"
              size="sm"
              disabled={loading}
              onClick={() => void openSimilar(n.id)}
            >
              Похожие
            </Button>
          </li>
        ))}
        {!loading && niches.length === 0 && (
          <p className="text-muted-foreground text-sm">Нет данных — добавьте ниши в БД или seed.</p>
        )}
      </ul>
      {selectedId != null && similar.length > 0 && (
        <section className="space-y-2 border-t pt-4">
          <h2 className="text-lg font-medium">Похожие на #{selectedId}</h2>
          <ul className="space-y-2">
            {similar.map((s) => (
              <li key={s.id} className="text-sm border rounded p-3">
                <span className="font-medium">{s.title}</span>
                {s.score != null && (
                  <span className="text-muted-foreground ml-2">· {s.score}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export default App
