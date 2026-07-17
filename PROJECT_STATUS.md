# Where things stand — 2026-07-17 (updated)

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

Since the last update, two things happened:

1. We looked at that one-example comparison together, it looked sensible, and then we
   wrote down clear, concrete rules for what counts as "the AI got it right" vs "the AI
   messed up" — grasp distance thresholds, rotation thresholds, joint-angle thresholds,
   and how to combine the "thinking" AI's plan with the "doing" AI's movements into one
   verdict per example. Written down before running at scale, on purpose, so we're not
   inventing the rules after seeing which way the results lean.
2. We built the actual automatic scoring system that applies those rules, as one
   notebook that runs start to finish on Colab: it plays out a task, watches for the
   moment the robot's hand closes around the object and the moment it lets go, and uses
   those two moments to split the task into three parts — reach, carry, and let-go. Then
   it asks both AIs what they'd do at the start of each of those three parts, writes down
   what they predicted next to what the human actually did, and applies the rules from
   step 1 — was the movement close enough, was the plan sensible and in the right order —
   to produce a table showing, for each of those three parts of each example, whether the
   two AIs succeeded together, failed together, or (the case we care about most) the plan
   was right but the movement wasn't — meaning the intent got lost somewhere between
   "deciding what to do" and "actually doing it."

It hasn't been run yet — it needs a live Colab session with a GPU, same as everything
else so far. The scoring math inside it has been tested with made-up example data and
checks out, but hasn't seen real output yet either.

## What's next

1. Run the notebook on Colab across a batch of examples and look at the resulting table
   together — does the automatic scoring line up with what a person would say looking at
   the same examples?
2. If it looks reasonable, scale up further: run this across many more examples, spot-
   check a chunk of them by hand, and build the final chart/table for the paper showing
   where and how these AIs tend to lose the thread between "figuring out what to do" and
   "actually doing it."

## Two things worth remembering

- The "thinking" AI we're using isn't literally part of the "doing" AI — it's a
  reasonable stand-in, because we can't actually see the doing AI's internal
  reasoning directly. Good enough to use, but not the exact same thing.
- The hand-position numbers we calculated ourselves (step 2 above) are our best
  estimate from geometry, not something the robot itself measured. Reasonable, but an
  approximation we should keep flagging, not treat as ground truth.
