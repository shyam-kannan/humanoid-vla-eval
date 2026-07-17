# Where things stand — 2026-07-17

## What we did

We got the two AI models talking to real robot data and to each other, and confirmed
they both produce sensible output on a real example.

Here's the flow in plain terms:

1. **Picked the data.** We needed real recordings of a humanoid robot (Unitree G1)
   doing tasks — a human remote-controlling the robot, with everything the robot's
   joints did saved, plus video and a text description of the task ("pick up the red
   apple and place it on the plate"). Our first choice of dataset turned out not to be
   compatible with the "doing" AI — it would've needed extra training to understand
   that robot's specific movements, which our compute budget doesn't allow. Switched to
   a different real-robot dataset that works without any extra training.

2. **Hit a gap and filled it.** The "doing" AI expects to know exactly where the
   robot's hand is in 3D space. The recordings only tell us how bent each joint is
   (shoulder, elbow, wrist), not where the hand ends up. So we calculated it ourselves —
   basic geometry, using the robot's exact body measurements (like knowing exactly how
   long someone's forearm and upper arm are, you can calculate where their hand is if
   you know how bent their elbow and shoulder are). We checked the numbers came out
   sensible (roughly arm's-length from the body, not some impossible position).

3. **Got both AIs running and talking to the data.** One AI acts like the "thinking"
   part — given a task and a picture, it writes out the steps it would take. The other
   acts like the "doing" part — given the same task and the robot's current pose, it
   predicts what the robot's joints should do next. Both are now working: we fed them
   one real example (pick up the apple, put it on the plate) and both gave sensible
   answers. The thinking AI wrote out a reasonable step-by-step plan. The doing AI
   predicted a plausible arm movement.

4. **Worked through a bunch of setup friction.** Getting everything installed and
   talking to each other correctly on Google Colab took a lot of trial and error —
   wrong assumptions about how to call these models, a nasty software conflict during
   installation, that sort of thing. All resolved now; the setup should run smoothly
   for anyone starting fresh.

## Where we are right now

We just added a check that compares what the "doing" AI predicted against what the
human actually did when controlling the robot for that same example — to see, by eye,
how close the prediction is. That comparison is written but hasn't been run yet.

## What's next

1. Run that comparison and look at it together — does the predicted movement roughly
   match what the human did? Does the AI's step-by-step plan make sense?
2. Once that looks reasonable, we write down clear, concrete rules for what counts as
   "the AI got it right" vs "the AI messed up" — before running this on a lot of
   examples, so we're not making up the rules after seeing the results.
3. Then scale up: run this across many examples automatically, spot-check a chunk of
   them by hand, and build the final chart/table showing where and how these AIs tend
   to lose the thread between "figuring out what to do" and "actually doing it."

## Two things worth remembering

- The "thinking" AI we're using isn't literally part of the "doing" AI — it's a
  reasonable stand-in, because we can't actually see the doing AI's internal
  reasoning directly. Good enough to use, but not the exact same thing.
- The hand-position numbers we calculated ourselves (step 2 above) are our best
  estimate from geometry, not something the robot itself measured. Reasonable, but an
  approximation we should keep flagging, not treat as ground truth.
