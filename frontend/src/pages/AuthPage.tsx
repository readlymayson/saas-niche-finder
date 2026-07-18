import { useState, type FormEvent } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { login, register } from "@/lib/api"

export function AuthPage() {
  const location = useLocation()
  const isRegister = location.pathname === "/register"
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const tokens = isRegister ? await register(email, password) : await login(email, password)
      localStorage.setItem("access_token", tokens.access_token)
      localStorage.setItem("refresh_token", tokens.refresh_token)
      localStorage.setItem("user_email", email)
      navigate("/dashboard")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка авторизации")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-md w-full space-y-4">
        <h1 className="text-2xl font-semibold text-center">
          {isRegister ? "Регистрация" : "Вход"}
        </h1>
        <form onSubmit={(e) => void onSubmit(e)} className="space-y-3">
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
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "…" : isRegister ? "Создать аккаунт" : "Войти"}
          </Button>
        </form>
        <p className="text-sm text-center text-muted-foreground">
          <Link to="/" className="underline">
            На главную
          </Link>
          {" · "}
          <Link to={isRegister ? "/login" : "/register"} className="underline">
            {isRegister ? "Уже есть аккаунт" : "Регистрация"}
          </Link>
        </p>
      </div>
    </div>
  )
}
