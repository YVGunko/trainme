'use client';

import { useEffect, useState } from 'react';

export function EnglishCheck({ text, onApply, placement = 'sheet' }) {
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
        setError(data.error || 'Проверка не удалась');
        return;
      }
      setResult({ ...data.result, source: text.trim() });
    } catch {
      setResult(null);
      setError('Проверка не удалась');
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
  }

  return (
    <>
      <button type="button" className="secondary english-ask" onClick={check} disabled={empty || pending}>
        {pending ? 'Проверка...' : 'Проверить английский'}
      </button>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        placement === 'sheet' ? (
          <div className="english-layer">
            <button type="button" className="english-backdrop" aria-label="Закрыть" onClick={close} />
            <section className="english-sheet" role="dialog" aria-label="Проверка английского">
              <Review result={result} onApply={apply} onClose={close} />
            </section>
          </div>
        ) : (
          <div className="english-inline">
            <Review result={result} onApply={apply} onClose={close} />
          </div>
        )
      ) : null}
    </>
  );
}

function Review({ result, onApply, onClose }) {
  return (
    <>
      <div className="section-head">
        <h3>Проверка английского</h3>
        <button type="button" className="secondary english-ask" onClick={onClose}>
          Закрыть
        </button>
      </div>
      <div>
        <h4>Ваш текст</h4>
        <p>{result.source || ''}</p>
      </div>
      <div>
        <h4>Более ясная версия</h4>
        <p>{result.revision}</p>
      </div>
      <div>
        <h4>На что обратить внимание</h4>
        <ul className="english-tips">
          {(result.tips || []).map((tip) => (
            <li key={tip.aspect}>
              <strong>{tip.aspect}.</strong> {tip.note}
            </li>
          ))}
        </ul>
      </div>
      <button type="button" onClick={onApply}>
        Подставить в поле
      </button>
    </>
  );
}
