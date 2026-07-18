import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { fetchNiche, fetchSimilarNiches, type NicheCard } from "@/lib/api"

export function NicheDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [niche, setNiche] = useState<NicheCard | null>(null)
  const [similar, setSimilar] = useState<NicheCard[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      navigate("/login")
      return
    }
    const nicheId = Number(id)
    if (!nicheId) return
    void (async () => {
      try {
        setNiche(await fetchNiche(nicheId))
        setSimilar(await fetchSimilarNiches(nicheId))
      } catch (e) {
        setError(e instanceof Error ? e.message : "Ошибка")
      }
    })()
  }, [id, navigate])

  if (error) return <p className="p-8 text-red-600">{error}</p>
  if (!niche) return <p className="p-8 text-muted-foreground">Загрузка…</p>

  return (
    <div className="min-h-screen p-8 max-w-2xl mx-auto space-y-6">
      <Button variant="outline" asChild>
        <Link to="/dashboard">← Дашборд</Link>
      </Button>
      <article className="space-y-3 border rounded-lg p-6">
        <h1 className="text-2xl font-semibold">{niche.title}</h1>
        <p className="text-sm text-muted-foreground">{niche.slug}</p>
        {niche.summary && <p className="text-sm leading-relaxed">{niche.summary}</p>}
        {niche.score != null && <p className="text-sm">Score: {niche.score}</p>}
      </article>
      {similar.length > 0 && (
        <section>
          <h2 className="text-lg font-medium mb-2">Похожие</h2>
          <ul className="space-y-2">
            {similar.map((s) => (
              <li key={s.id}>
                <Link to={`/niche/${s.id}`} className="text-sm hover:underline">
                  {s.title}
                  {s.score != null ? ` · ${s.score}` : ""}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
