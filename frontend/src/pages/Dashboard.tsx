import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { fetchTopNiches, searchNiches, type NicheCard } from "@/lib/api"

export function Dashboard() {
  const navigate = useNavigate()
  const [niches, setNiches] = useState<NicheCard[]>([])
  const [searchQ, setSearchQ] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      setNiches(await fetchTopNiches(10))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      navigate("/login")
      return
    }
    void load()
  }, [load, navigate])

  const onSearch = async () => {
    if (!searchQ.trim()) return
    setLoading(true)
    setError(null)
    try {
      setNiches(await searchNiches(searchQ.trim()))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка поиска")
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    localStorage.clear()
    navigate("/")
  }

  return (
    <div className="min-h-screen p-8 max-w-3xl mx-auto space-y-6">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">Дашборд ниш</h1>
          <p className="text-sm text-muted-foreground">Топ по скорингу</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/account">Личный кабинет</Link>
          </Button>
          <Button variant="outline" onClick={logout}>
            Выйти
          </Button>
        </div>
      </header>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void load()} disabled={loading}>
          Обновить
        </Button>
        <input
          className="border rounded-md px-3 py-2 text-sm flex-1 min-w-[12rem]"
          placeholder="Поиск…"
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
            <Link to={`/niche/${n.id}`} className="font-medium hover:underline">
              {n.title}
            </Link>
            <div className="text-sm text-muted-foreground">{n.slug}</div>
            {n.score != null && <p className="text-xs mt-1">Score: {n.score}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}
