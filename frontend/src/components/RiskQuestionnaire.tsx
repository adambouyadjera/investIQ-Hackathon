import { useState } from 'react';
import { getQuestions, scoreQuestionnaire } from '../api/portfolio';
import { Button } from './ui/Button';
import { useEffect } from 'react';

interface Question {
  id: string;
  prompt: string;
  options: [string, number][];
}

interface Props {
  onResult: (tier: string) => void;
}

const TIER_DESCRIPTIONS: Record<string, { color: string; desc: string }> = {
  conservative: {
    color: 'text-blue-400',
    desc: 'You prefer stability and capital preservation. A mix of bonds and defensive assets suits you.',
  },
  balanced: {
    color: 'text-indigo-400',
    desc: 'You want growth but can handle moderate swings. A diversified equity/bond blend is your match.',
  },
  aggressive: {
    color: 'text-purple-400',
    desc: 'You can stomach volatility and are focused on long-term maximum growth. Heavy equity exposure fits.',
  },
};

export function RiskQuestionnaire({ onResult }: Props) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ risk_tier: string; percentile: number } | null>(null);

  useEffect(() => {
    getQuestions().then(setQuestions).catch(() => {});
  }, []);

  function handleAnswer(questionId: string, optionIndex: number) {
    setAnswers((prev) => ({ ...prev, [questionId]: optionIndex }));
  }

  async function handleSubmit() {
    if (Object.keys(answers).length < questions.length) return;
    setLoading(true);
    try {
      const res = await scoreQuestionnaire(answers as any);
      setResult(res);
      onResult(res.risk_tier);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  const complete = questions.length > 0 && Object.keys(answers).length === questions.length;

  return (
    <div className="flex flex-col gap-5 pt-4">
      {questions.map((q, qi) => (
        <div key={q.id}>
          <p className="text-sm font-medium text-gray-200 mb-2">
            {qi + 1}. {q.prompt}
          </p>
          <div className="flex flex-col gap-1.5">
            {q.options.map(([label], idx) => (
              <label key={idx} className="cursor-pointer flex items-center gap-2">
                <input
                  type="radio"
                  name={q.id}
                  checked={answers[q.id] === idx}
                  onChange={() => handleAnswer(q.id, idx)}
                  className="accent-indigo-500"
                />
                <span
                  className={`text-sm ${answers[q.id] === idx ? 'text-indigo-300' : 'text-gray-400'}`}
                >
                  {label}
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}

      {questions.length > 0 && (
        <Button
          onClick={handleSubmit}
          loading={loading}
          disabled={!complete}
          size="sm"
          className="w-40"
        >
          Get My Risk Profile
        </Button>
      )}

      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-700 p-4">
          <p className="text-xs text-gray-400 mb-1">Your risk profile:</p>
          <p className={`text-xl font-bold capitalize ${TIER_DESCRIPTIONS[result.risk_tier]?.color}`}>
            {result.risk_tier}
          </p>
          <p className="text-sm text-gray-400 mt-1">
            {TIER_DESCRIPTIONS[result.risk_tier]?.desc}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Score percentile: {(result.percentile * 100).toFixed(0)}%
          </p>
        </div>
      )}
    </div>
  );
}
