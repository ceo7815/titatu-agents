import { useEffect, useRef } from 'react'

type Node = {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  pulse: number
  champagne: boolean
}

const TAN = { r: 205, g: 186, b: 154 }
const WHITE = { r: 255, g: 255, b: 255 }

export function TechBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const pointer = { x: -9999, y: -9999 }
    let nodes: Node[] = []
    let raf = 0
    let width = 0
    let height = 0

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      const count = reduced
        ? 18
        : width < 640
          ? 28
          : width < 1024
            ? 48
            : 72
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.28,
        vy: (Math.random() - 0.5) * 0.28,
        r: 1.1 + Math.random() * 1.8,
        pulse: Math.random() * Math.PI * 2,
        champagne: Math.random() > 0.45,
      }))
    }

    function onMove(event: PointerEvent) {
      pointer.x = event.clientX
      pointer.y = event.clientY
    }

    function onLeave() {
      pointer.x = -9999
      pointer.y = -9999
    }

    function step() {
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, width, height)

      const grid = 56
      ctx.strokeStyle = 'rgba(205,186,154,0.05)'
      ctx.lineWidth = 1
      for (let x = 0; x < width; x += grid) {
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
        ctx.stroke()
      }
      for (let y = 0; y < height; y += grid) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
        ctx.stroke()
      }

      const g1 = ctx.createRadialGradient(
        width * 0.28,
        height * 0.22,
        0,
        width * 0.28,
        height * 0.22,
        Math.max(width, height) * 0.55,
      )
      g1.addColorStop(0, 'rgba(205,186,154,0.16)')
      g1.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g1
      ctx.fillRect(0, 0, width, height)

      const g2 = ctx.createRadialGradient(
        width * 0.78,
        height * 0.78,
        0,
        width * 0.78,
        height * 0.78,
        Math.max(width, height) * 0.5,
      )
      g2.addColorStop(0, 'rgba(255,255,255,0.06)')
      g2.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g2
      ctx.fillRect(0, 0, width, height)

      const linkDist = width < 640 ? 92 : 132
      for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j += 1) {
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const dist = Math.hypot(dx, dy)
          if (dist > linkDist) continue
          const alpha = (1 - dist / linkDist) * 0.28
          const c = a.champagne || b.champagne ? TAN : WHITE
          ctx.strokeStyle = `rgba(${c.r},${c.g},${c.b},${alpha})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(b.x, b.y)
          ctx.stroke()
        }
      }

      for (const node of nodes) {
        if (!reduced) {
          node.x += node.vx
          node.y += node.vy
          node.pulse += 0.018
        }
        if (node.x < -20) node.x = width + 20
        if (node.x > width + 20) node.x = -20
        if (node.y < -20) node.y = height + 20
        if (node.y > height + 20) node.y = -20

        const dx = node.x - pointer.x
        const dy = node.y - pointer.y
        const near = Math.hypot(dx, dy)
        if (near < 140) {
          node.x += dx * 0.004
          node.y += dy * 0.004
        }

        const c = node.champagne ? TAN : WHITE
        const glow = 0.45 + Math.sin(node.pulse) * 0.25
        ctx.beginPath()
        ctx.fillStyle = `rgba(${c.r},${c.g},${c.b},${0.55 + glow * 0.25})`
        ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2)
        ctx.fill()
        ctx.beginPath()
        ctx.fillStyle = `rgba(${c.r},${c.g},${c.b},${0.08 + glow * 0.08})`
        ctx.arc(node.x, node.y, node.r * 6, 0, Math.PI * 2)
        ctx.fill()
      }

      raf = requestAnimationFrame(step)
    }

    resize()
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('pointerleave', onLeave)
    raf = requestAnimationFrame(step)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  return <canvas className="login-canvas" ref={canvasRef} aria-hidden="true" />
}
