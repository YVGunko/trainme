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

  function apply(next) {
    const value = typeof next === 'string' ? next : result?.revision;
    if (!value) return;
    onApply(value);
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

function toneLabel(tone) {
  const names = { casual: 'Casual', polite: 'Polite', british: 'British', american: 'American' };
  const key = String(tone || '').toLowerCase();
  return names[key] || key;
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
      {result.verdict ? (
        <div>
          <h4>Does it sound right</h4>
          <p>{result.verdict}</p>
        </div>
      ) : null}
      <div>
        <h4>British version</h4>
        <p>{result.revision}</p>
      </div>
      <div>
        <h4>Other ways to say it</h4>
        <ul className="english-alts">
          {(result.alternatives || []).map((item, index) => (
            <li key={`${item.tone}-${index}`}>
              <p>
                <strong>{toneLabel(item.tone)}.</strong> {item.text}
              </p>
              <IconButton icon="check" label={`Apply ${toneLabel(item.tone)}`} onClick={() => onApply(item.text)} />
            </li>
          ))}
        </ul>
      </div>
      {(result.tweaks || []).length > 0 ? (
        <div>
          <h4>Small tweaks</h4>
          <ul className="english-tips">
            {result.tweaks.map((tweak, index) => (
              <li key={`${tweak.aspect}-${index}`}>
                <strong>{tweak.aspect}.</strong> {tweak.note}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
