import { CursorPosition } from '../store/appStore';

export function drawFrameToCanvas(
  canvas: HTMLCanvasElement,
  base64Png: string,
  cursor?: CursorPosition | null
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const image = new Image();
  image.onload = () => {
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    const scale = Math.min(width / image.width, height / image.height);
    const drawWidth = image.width * scale;
    const drawHeight = image.height * scale;
    const offsetX = (width - drawWidth) / 2;
    const offsetY = (height - drawHeight) / 2;
    ctx.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);
    if (cursor && typeof cursor.x === 'number' && typeof cursor.y === 'number') {
      const x = offsetX + drawWidth * cursor.x;
      const y = offsetY + drawHeight * cursor.y;
      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.arc(x, y, 12, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = 'rgba(56, 189, 248, 0.35)';
      ctx.fill();
      ctx.restore();
    }
  };
  image.src = `data:image/png;base64,${base64Png}`;
}
