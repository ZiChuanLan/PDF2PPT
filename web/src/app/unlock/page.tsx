import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"

type UnlockPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function readStringParam(
  source: Record<string, string | string[] | undefined>,
  key: string
): string {
  const value = source[key]
  if (Array.isArray(value)) return String(value[0] || "")
  return String(value || "")
}

export default async function UnlockPage({ searchParams }: UnlockPageProps) {
  const resolvedSearchParams = (await searchParams) || {}
  const nextPath = readStringParam(resolvedSearchParams, "next") || "/"
  const hasError = readStringParam(resolvedSearchParams, "error") === "1"

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
      <Card className="w-full max-w-xl border-border bg-background/95 backdrop-blur">
        <CardHeader className="border-b border-border">
          <CardTitle>访问密码</CardTitle>
          <CardDescription>
            当前站点已开启前端访问保护。输入密码后才能打开工作台页面。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          <form action="/unlock/submit" method="post" className="space-y-5">
            <input type="hidden" name="next" value={nextPath} />
            <label className="block space-y-2">
              <span className="font-sans text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Site Password
              </span>
              <Input
                name="password"
                type="password"
                autoFocus
                autoComplete="current-password"
                placeholder="输入访问密码"
              />
            </label>

            {hasError ? (
              <p className="font-sans text-sm text-destructive">
                密码不正确，请重新输入。
              </p>
            ) : null}

            <div className="flex items-center justify-between gap-3">
              <p className="font-sans text-sm text-muted-foreground">
                解锁成功后会在当前浏览器保留一段时间。
              </p>
              <Button type="submit">解锁站点</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
