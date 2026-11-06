import DownloadIcon from '@mui/icons-material/Download';
import LinkIcon from '@mui/icons-material/Link';
import { Button, ButtonGroup, Menu, MenuItem, Snackbar } from '@mui/material';
import { getNodesBounds, getViewportForBounds, useReactFlow } from '@xyflow/react';
import { toJpeg, toPng, toSvg } from 'html-to-image';
import { useState } from 'react';
import type { Integration } from '../../api/types';

const PAD = 40;
const MAX_SIDE = 5000;

function download(dataUrl: string, filename: string) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
}

/** FR-15: export the current diagram (with highlighting) as PNG, SVG or PDF, or copy a deep link. */
export default function ExportMenu({ integration, title }: { integration: Integration | null; title: string }) {
  const { getNodes } = useReactFlow();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [message, setMessage] = useState('');

  async function render(kind: 'png' | 'svg' | 'jpeg') {
    const bounds = getNodesBounds(getNodes());
    const width = Math.min(MAX_SIDE, Math.ceil(bounds.width + PAD * 2));
    const height = Math.min(MAX_SIDE, Math.ceil(bounds.height + PAD * 2));
    const vp = getViewportForBounds(bounds, width, height, 0.1, 2, 0.02);
    const el = document.querySelector<HTMLElement>('.react-flow__viewport');
    if (!el) throw new Error('Diagram not ready');
    const options = {
      backgroundColor: '#ffffff',
      width,
      height,
      pixelRatio: kind === 'svg' ? 1 : 2,
      quality: 0.9,
      style: { width: `${width}px`, height: `${height}px`, transform: `translate(${vp.x}px, ${vp.y}px) scale(${vp.zoom})` },
    };
    const fn = kind === 'png' ? toPng : kind === 'jpeg' ? toJpeg : toSvg;
    return { url: await fn(el, options), width, height };
  }

  const baseName = integration ? `flow-${integration.id}` : 'architecture';

  async function exportAs(kind: 'png' | 'svg' | 'pdf') {
    setAnchor(null);
    try {
      if (kind !== 'pdf') {
        const { url } = await render(kind);
        download(url, `${baseName}.${kind}`);
        return;
      }
      const [{ url, width, height }, { jsPDF }] = await Promise.all([render('jpeg'), import('jspdf')]);
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const margin = 32;
      pdf.setFontSize(16);
      pdf.text(title, margin, margin + 8);
      pdf.setFontSize(9);
      pdf.text(`Generated ${new Date().toLocaleString()} · ${window.location.href}`, margin, margin + 24, { maxWidth: pageW - margin * 2 });
      const top = margin + 40;
      const scale = Math.min((pageW - margin * 2) / width, (pageH - top - margin) / height);
      pdf.addImage(url, 'JPEG', margin, top, width * scale, height * scale);
      if (integration) {
        pdf.addPage();
        pdf.setFontSize(14);
        pdf.text(`${integration.name} — step by step`, margin, margin + 8);
        pdf.setFontSize(10);
        let y = margin + 32;
        for (const line of integration.narrative) {
          const wrapped = pdf.splitTextToSize(line, pageW - margin * 2) as string[];
          if (y + wrapped.length * 13 > pageH - margin) {
            pdf.addPage();
            y = margin;
          }
          pdf.text(wrapped, margin, y);
          y += wrapped.length * 13 + 4;
        }
      }
      pdf.save(`${baseName}.pdf`);
    } catch (e) {
      setMessage(`Export failed: ${(e as Error).message}`);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setMessage('Link copied to clipboard');
    } catch {
      setMessage(window.location.href);
    }
  }

  return (
    <>
      <ButtonGroup size="small" variant="outlined" sx={{ bgcolor: 'background.paper' }}>
        <Button startIcon={<DownloadIcon />} onClick={(e) => setAnchor(e.currentTarget)} aria-haspopup="menu">
          Export
        </Button>
        <Button startIcon={<LinkIcon />} onClick={copyLink}>
          Copy link
        </Button>
      </ButtonGroup>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => exportAs('png')}>PNG image</MenuItem>
        <MenuItem onClick={() => exportAs('svg')}>SVG image</MenuItem>
        <MenuItem onClick={() => exportAs('pdf')}>PDF (diagram + narrative)</MenuItem>
      </Menu>
      <Snackbar open={Boolean(message)} autoHideDuration={4000} onClose={() => setMessage('')} message={message} />
    </>
  );
}
