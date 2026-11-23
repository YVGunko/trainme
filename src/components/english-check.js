'use client';

import { useEffect, useState } from 'react';
import { IconButton } from '@/components/icon-button';

export function EnglishCheck({ text, onApply, placement = 'sheet', label, fieldId, children }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const empty = !text.trim();

  async function check() {
    if (pending || empty) return;
    setPending(true);
    setError('');
    try {
      const response = await fetch('/api/english', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setResult(null);
        setError(data.error || 'The check failed');
        return;
      }
      setResult({ ...data.result, source: text.trim() });
    } catch {
      setResult(null);
      setError('The check failed');
    } finally {
      setPending(false);
    }
  }

  useEffect(() => {
    if (!result || placement !== 'sheet') return undefined;
    function onKey(event) {
      if (event.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [result, placement]);

  function close() {
    setResult(null);
    setError('');
  }

  function apply() {
    if (!result?.revision) return;
    onApply(result.revision);
    close();
  }

  const review = result ? <Review result={result} onApply={apply} onClose={close} /> : null;

  return (
    <div className="note-field">
      <div className="field-head">
        <label htmlFor={fieldId}>{label}</label>
        <IconButton
          icon="spell"
          variant="secondary"
          label={pending ? 'Checking...' : 'Check English'}
          busy={pending}
          disabled={empty}
          onClick={check}
        />
      </div>
      {children}
      {error ? <p className="error">{error}</p> : null}
      {placement === 'sheet' && result ? (
        <div className="english-layer">
          <button type="button" className="english-backdrop" aria-label="Close" onClick={close} />
          <section className="english-sheet" role="dialog" aria-label="English check">
            {review}
          </section>
        </div>
      ) : null}
      {placement === 'inline' && result ? <div className="english-inline">{review}</div> : null}
    </div>
  );
}

function Review({ result, onApply, onClose }) {
  return (
    <>
      <div className="section-head">
        <h3>English check</h3>
        <div className="icon-row">
          <IconButton icon="check" label="Apply to field" onClick={onApply} />
          <IconButton icon="close" variant="secondary" label="Close" onClick={onClose} />
        </div>
      </div>
      <div>
        <h4>Your text</h4>
        <p>{result.source || ''}</p>
      </div>
      <div>
        <h4>Clearer version</h4>
        <p>{result.revision}</p>
      </div>
      <div>
        <h4>What to notice</h4>
        <ul className="english-tips">
          {(result.tips || []).map((tip) => (
            <li key={tip.aspect}>
              <strong>{tip.aspect}.</strong> {tip.note}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
