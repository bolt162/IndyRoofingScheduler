"""
Approved customer copy: "Build Queue Weekly Email Cadence".

Edit wording here only with Aaron's approval. Rules for any change:
  - no dashes (em dashes or dashed asides) in customer copy
  - never a date or week estimate; "builds ahead of you" is the only progress number
  - never mention location or neighborhood as a reason the order changes

Placeholders in {braces} are filled by compose.py. A few placeholders are whole
phrases (e.g. {roof_materials}) so a missing color or product reads naturally
instead of leaving a blank.
"""

TEAM_SIGNOFF = "The Indy Roof and Restoration Team"

TOP_LINE = (
    "This is an automated update from a no reply address. Please don't reply to this email. "
    "Questions? Call us at (317) 886-7436."
)

FOOTER_WITH_REP = (
    "Replies to this email are not received or read. For questions about your project, call or "
    "text us at (317) 886-7436 or reach out to {rep_name} directly at {rep_phone}. "
    "We're always happy to help."
)
FOOTER_NO_REP = (
    "Replies to this email are not received or read. For questions about your project, call or "
    "text us at (317) 886-7436. We're always happy to help."
)

# ---------------------------------------------------------------------------
# {position_block}
# ---------------------------------------------------------------------------
POSITION_DROPPED = "{ahead_now}, {delta} fewer than last week."
POSITION_DROPPED_BUILDS = "Our crews finished {builds_completed} this week."
POSITION_SAME = (
    "You're holding strong with {ahead_count}. Our crews spent this week on some bigger, more "
    "detailed projects, and your spot is locked in."
)
POSITION_UP = (
    "Your spot is locked in and you're moving toward the front. Each week we balance the schedule "
    "around weather, crews, materials, and the size of each project, so the order can shift a "
    "little from week to week."
)
# Below the countdown floor (compose.COUNT_FLOOR) we stop showing a number.
# First sentence of POSITION_UP, so it's approved wording.
POSITION_NEAR_FRONT = "Your spot is locked in and you're moving toward the front."
WELCOME_NEAR_FRONT = "**your spot is locked in and you're moving toward the front.**"
# Used only when there's no snapshot from a prior email to compare against
POSITION_FIRST = "You're holding strong with {ahead_count}."

# ---------------------------------------------------------------------------
# Day 0: Welcome (all trades)
# ---------------------------------------------------------------------------
WELCOME_SUBJECT = "You're officially on the build schedule, {first_name}"
WELCOME_BODY = """
Great news. Your {project_word} is officially in our build queue, and we couldn't be more excited to get to work on your home.

Here's how it works. Every project that's ready to build goes into our schedule. The biggest factor in when you get built is how long you've been waiting, so the line moves forward every single week. Each week we also balance the schedule around weather, crew availability, materials, and the size of each project, so the order can shift a little from week to week. Nobody gets skipped, and nobody gets forgotten.

Right now {ahead_bold}

We can't promise an exact date yet, because weather and the size of the projects ahead of you both play a part. What we can promise is that you'll hear from us every Thursday with an update on where you stand, plus a few tips to help you get the most out of your new {project_word}.

Thanks for choosing Indy Roof and Restoration. We're glad you're here.

The Indy Roof and Restoration Team
"""

# ---------------------------------------------------------------------------
# ROOF TRACK
# ---------------------------------------------------------------------------
ROOF_W1_SUBJECT = "What's happening behind the scenes on your roof"
ROOF_W1_BODY = """
{position_block}

Even while you're waiting, a lot is already moving on your project. Before any crew pulls into a driveway, our team lines up the details that make build day go smoothly:

- **Materials.** {roof_materials_bullet}
- **Permits.** Where your city or county requires one, we handle the paperwork.
- **Crew planning.** We match each roof with a crew that fits the size and pitch of the job.

{color_tip}

Talk soon,

The Indy Roof and Restoration Team
"""
ROOF_W1_MATERIALS = "We confirm {roof_materials}, plus the underlayment, flashing, vents, and drip edge your roof needs."
ROOF_W1_MATERIALS_LOW_SLOPE = "We confirm the membrane, insulation, flashing, and drainage details your low slope roof needs."
ROOF_W1_COLOR_TIP = (
    "**Quick tip:** If you've had second thoughts about your color, now is the perfect time to let us "
    "know. Once materials are ordered for your build, changes get harder. Just give us a call."
)

INSURANCE_SUBJECT = "A tip that could lower your insurance bill"
ROOF_W2_A_BODY = """
{position_block}

Here's one most homeowners never hear about. Your new {shingle_line} shingles carry a Class 4 impact rating, the highest rating a shingle can earn for hail resistance.

Many insurance carriers reward Class 4 shingles with a discount on your homeowners premium. It isn't automatic, so it pays to ask. Once your roof is installed:

1. Call your insurance agent and tell them you have a new roof with Class 4 impact resistant shingles.
2. Ask if you qualify for a **new roof discount** and an **impact resistant shingle discount**. Some carriers offer both.
3. If they need proof, we'll provide paperwork showing the product, its rating, and the install date.

It's a five minute phone call that could save you money every year you own your home.

The Indy Roof and Restoration Team
"""
ROOF_W2_B_BODY = """
{position_block}

Here's a quick win once your roof is done. Many insurance carriers give a better rate on homes with a new roof, because a new roof means fewer claims. After your install, call your agent, let them know the roof was replaced, and ask what discounts apply.

While you're on the phone, mention that your {shingle_line} shingles carry a Class 3 impact rating, which means they're built to handle hail better than a standard shingle. Discount rules vary by carrier, and your agent can tell you whether it counts on your policy. If they need proof, we'll provide paperwork showing the product, its rating, and the install date.

It takes five minutes and could save you money every year.

The Indy Roof and Restoration Team
"""
ROOF_W2_C_BODY = """
{position_block}

Here's a quick win once your roof is done. Many insurance carriers give a better rate on homes with a newer roof, because a new roof means fewer claims. After your install, call your agent, let them know the roof was replaced, and ask if a new roof discount applies to your policy. If they need proof, we'll provide paperwork showing the install date.

It takes five minutes and could save you money every year.

The Indy Roof and Restoration Team
"""

ROOF_W3_SUBJECT = "5 easy ways to get ready for build day"
ROOF_W3_BODY = """
{position_block}

You don't need to do anything yet, but these are easy to plan for now so build day is stress free:

1. **Clear the driveway.** Our crew needs space for a dumpster and the material delivery. Plan to park on the street that day.
2. **Take down wall hangings.** Tear off and install send vibration through the house. Pictures and mirrors on exterior walls are safest on the floor.
3. **Cover the attic.** A little dust can fall through the decking. A drop cloth or old sheet over anything stored up there keeps it clean.
4. **Plan for pets.** Build day is loud. Many pets are happiest with a friend, family member, or doggy daycare for the day.
5. **Mark your yard.** Let your crew know about sprinkler heads, garden beds, or anything delicate near the house so we can protect it.

We'll send a full checklist again when you're close to the front of the line.

The Indy Roof and Restoration Team
"""

ROOF_W4_SUBJECT = "Here's exactly what build day looks like"
ROOF_W4_BODY = """
{position_block}

Most normal sized roofs are completed in a single day. Larger or more complex roofs, like steep pitches, multiple layers to tear off, or lots of angles and valleys, may take more than one day, and your crew will let you know what to expect. Here's what build day looks like when it's your turn:

- **Early morning.** The crew arrives, sets up, and lays tarps to protect your landscaping and siding.
- **Tear off.** The old roof comes off down to the wood decking. This is the loudest part.
- **Inspection.** We check the decking and replace any soft or damaged boards so your new roof sits on a solid base.
- **Install.** {roof_install_bullet}
- **Cleanup.** We pick up debris and run magnetic sweepers across your yard and driveway to catch stray nails.
- **Walkthrough.** We make sure you're happy with the finished roof.

The best part? Seeing your home with a brand new roof when the crew wraps up. Our customers tell us it never gets old.

The Indy Roof and Restoration Team
"""
ROOF_W4_INSTALL = "Underlayment, flashing, vents, and {new_shingles} go on."
ROOF_W4_INSTALL_LOW_SLOPE = "Your new low slope roof system goes on, sealed at every seam, edge, and opening."

W5_SUBJECT_ROOF = "Why we'll never rush your roof"
W5_SUBJECT_PROJECT = "Why we'll never rush your project"
W5_BODY = """
{position_block}

{w5_opener}

{w5_conditions}

That's also why we can't give exact dates while you're in the queue. A week of rain, snow, or deep cold pauses every crew, and a stretch of good weather lets us move fast. Either way, your spot is held and the line keeps moving.

{w5_tip}

The Indy Roof and Restoration Team
"""
W5_OPENER_ROOF = (
    "If you've been watching the forecast and wondering how it affects your build, you're thinking "
    "like a roofer."
)
# Siding and gutter version drops the roof wording (see handoff Part 6, Week 5 note)
W5_OPENER_PROJECT = (
    "If you've been watching the forecast and wondering how it affects your build, you're thinking "
    "like a pro."
)
W5_CONDITIONS_ROOF = (
    "We don't install during rain, snow, or any other precipitation, and we keep a close eye on wind "
    "and temperature too. {w5_material_sentence} In colder months, we hold ourselves to a cold weather "
    "limit that's stricter than the manufacturer requires. When the weather turns, we'd rather wait a "
    "day than cut a corner on your home."
)
W5_SHINGLE_SENTENCE = (
    "Shingles seal to each other using heat, so the conditions on build day matter for how well your "
    "roof holds up for decades."
)
W5_LOW_SLOPE_SENTENCE = (
    "Low slope roofs need dry surfaces and the right temperatures for seams and adhesives to bond "
    "properly, so the conditions on build day matter for how well your roof holds up for decades."
)
W5_CONDITIONS_SIDING = (
    "Rain, snow, high wind, and extreme temperatures all affect how siding goes on. Some materials "
    "expand and contract with temperature, and installing them right means doing it in the right "
    "conditions. When the weather turns, we'd rather wait a day than cut a corner on your home."
)
W5_CONDITIONS_GUTTERS = (
    "Ladders and wet or icy rooflines don't mix, so we keep our crews off the edges during rain, "
    "snow, ice, and high wind. When the weather turns, we'd rather wait a day than take chances with "
    "your home or our crew."
)
W5_TIP_ROOF = (
    "**Quick tip:** Snap a few photos of your current roof and attic this week. They're nice to have "
    "for your records and fun to compare once the new roof is on."
)

ROOF_TIPS = [
    "Clean out your gutters before build day so we can see their condition and check that water drains well from your new roof.",
    "Trim tree branches hanging over the roof. It protects your new shingles and keeps leaves off the surface.",
    "Check your attic for good airflow. Proper ventilation helps shingles last longer, and our crew will review it on build day.",
    "After a big storm, walk around your house and look for missing shingles or debris. Catching small things early saves big headaches.",
    "Keep a home folder for your roof paperwork, warranty, and insurance documents. You'll thank yourself later.",
    "Thinking about solar panels or skylights someday? Let us know before build day so we can plan for it.",
    "If your carrier offers a new roof discount, set a reminder to call them the week after your build.",
]

# ---------------------------------------------------------------------------
# SIDING TRACK
# ---------------------------------------------------------------------------
SIDING_W1_SUBJECT = "What's happening behind the scenes on your siding"
SIDING_W1_BODY = """
{position_block}

Even while you wait, your project is already moving. Before a crew arrives, we confirm {siding_desc}, along with the trim, house wrap, and accessories your home needs. Where your city requires a permit, we handle that too, and we match your home with a crew that fits the size of the job.

**Quick tip:** Still deciding on trim color, or wondering how your color looks in different light? Now is the perfect time to ask. Once materials are ordered, changes get harder.

The Indy Roof and Restoration Team
"""

SIDING_W2_SUBJECT = "Two easy ways to get more from your new siding"
SIDING_W2_BODY = """
{position_block}

**Ask for a few spare pieces.** Colors and profiles change over the years. Keeping a few leftover pieces in the garage makes a future repair from a stray baseball or storm a simple fix that matches perfectly.

**Save your project paperwork.** New siding is one of the most noticed upgrades when a home sells. Keeping your product details and warranty together makes it easy to show buyers exactly what's on the house.

The Indy Roof and Restoration Team
"""

SIDING_W3_SUBJECT = "5 easy ways to get ready for your siding install"
SIDING_W3_BODY = """
{position_block}

Nothing to do yet, but these are easy to plan for now:

1. **Clear a path around the house.** Move patio furniture, grills, planters, and decor about 10 feet from the walls.
2. **Take down wall hangings.** Pictures and mirrors on exterior walls are safest on the floor while we work.
3. **Remove outdoor fixtures you want to keep.** Think doorbell cameras, house numbers, hose reels, and flag mounts. We'll reinstall what goes back on.
4. **Trim shrubs near the house.** A little space lets the crew work cleanly and protects your plants.
5. **Plan for pets and parking.** Siding work is noisy and the crew needs driveway space for materials.

The Indy Roof and Restoration Team
"""

SIDING_W4_SUBJECT = "Here's what your siding install will look like"
SIDING_W4_BODY = """
{position_block}

Most siding projects take a few days, depending on the size of the home. Here's the flow:

- **Setup.** The crew protects landscaping and sets up materials.
- **Removal.** Old siding comes off one section at a time, so your home is never left wide open.
- **Inspection.** We check the sheathing underneath and repair any damaged areas.
- **House wrap.** A weather barrier goes on to help keep moisture out.
- **Install.** Trim, corners, and {new_siding} go up.
- **Cleanup and walkthrough.** We clean up daily and walk the finished project with you.

The Indy Roof and Restoration Team
"""

SIDING_TIPS = [
    "Rinse your siding once a year with a garden hose to keep it looking new; skip the pressure washer.",
    "Keep sprinklers aimed away from your walls.",
    "Keep mulch and soil a few inches below the bottom row of siding.",
    "Trim shrubs so they don't rub against the house.",
    "After a hail storm, walk around and look for dents or cracks.",
    "Keep your spare pieces somewhere dry.",
]

# ---------------------------------------------------------------------------
# GUTTER TRACK
# ---------------------------------------------------------------------------
GUTTER_W1_SUBJECT = "How your new gutters are made"
GUTTER_W1_BODY = """
{position_block}

Here's something most people don't know. Your new 6 inch seamless gutters are formed right on site, on a machine in our truck, measured to the exact length of your home. Six inch gutters carry a lot more water than the standard five inch size, which matters during a hard Indiana downpour. Fewer seams means fewer spots for leaks. Before install day, we confirm {gutter_color_desc}, downspout locations, and any guards you've chosen.

The Indy Roof and Restoration Team
"""

GUTTER_W2_SUBJECT = "One quick decision that protects your foundation"
GUTTER_W2_BODY = """
{position_block}

The whole job of a gutter is to move water away from your house. Take a quick walk around your home this week and notice where water pools after a rain, or where a downspout dumps near a patio or walkway. If you'd like a downspout moved or extended, let us know before install day and we'll plan for it.

The Indy Roof and Restoration Team
"""

GUTTER_W3_SUBJECT = "Getting ready for your gutter install is easy"
GUTTER_W3_BODY = """
{position_block}

1. **Clear the ground under your eaves.** Move furniture, planters, and anything fragile from along the walls.
2. **Leave driveway space.** Our gutter truck forms your gutters on site and needs room to park.
3. **Flag what's underground.** Let us know about sprinkler lines or buried drain lines near downspouts.
4. **Unlock gates** so the crew can reach every side of the house.

The Indy Roof and Restoration Team
"""

GUTTER_W4_SUBJECT = "Here's what gutter install day looks like"
GUTTER_W4_BODY = """
{position_block}

Most gutter installs take just a few hours. The crew removes your old gutters, checks the fascia boards behind them, forms your new seamless gutters right in the driveway, hangs them with sturdy hidden hangers, and attaches the downspouts. Then we clean up and walk it with you.

The Indy Roof and Restoration Team
"""

GUTTER_TIPS = [
    "Clean gutters in late fall after the leaves drop, and again in spring.",
    "Gutter guards cut cleaning way down; ask us if you're curious.",
    "Make sure downspouts empty at least a few feet from the foundation.",
    "Watch for water spilling over the edge during a heavy rain; it usually means a clog.",
    "Trim branches that hang over the roofline.",
]

# ---------------------------------------------------------------------------
# REPAIR TRACK (roof repairs and siding repairs)
# Repairs vary too much for a build-day sequence, so they get a welcome and then a
# weekly check-in with a home care tip. No position numbers on repairs: they're often
# fit in around builds, so a count would look odd (ops request, 2026-10-03).
# DRAFT: written by Claude, pending Aaron's approval.
# ---------------------------------------------------------------------------
REPAIR_WELCOME_SUBJECT = "Your repair is on our schedule, {first_name}"
REPAIR_WELCOME_BODY = """
Great news. Your {repair_word} is officially on our schedule, and our team is ready to take care of it.

Here's how it works. Every repair that's ready gets a spot on our list, and the list moves forward every single week. Each week we balance the schedule around weather, crew availability, and materials. Nobody gets skipped, and nobody gets forgotten.

We can't promise an exact date yet, because weather plays a big part. What we can promise is that you'll hear from us every Thursday with a quick update, plus a tip to help you take care of your home.

{leak_note}

Thank you for your patience while we work through our customer list. We're glad you chose Indy Roof and Restoration.

The Indy Roof and Restoration Team
"""

REPAIR_WEEKLY_BODY = """
{opener}

**This week's tip:** {tip}

{leak_note}

Thanks for being patient while we work through our customer list.

The Indy Roof and Restoration Team
"""
# Roof repairs only: a leak can't wait for the list
REPAIR_LEAK_WITH_REP = (
    "**If a leak starts while you wait:** please call {rep_name}, the rep who signed you up, at "
    "{rep_phone}. We'll help get a tarp on to protect your home until your repair is done."
)
REPAIR_LEAK_NO_REP = (
    "**If a leak starts while you wait:** please call us at (317) 886-7436. We'll help get a tarp "
    "on to protect your home until your repair is done."
)
REPAIR_ROTATION = [
    ("Your repair is still on our schedule, {first_name}", "Just checking in to let you know your repair is on our schedule and working its way up the list."),
    ("A quick home care tip while you wait", "Another week of work in the books, and your repair keeps moving up the list."),
    ("We haven't forgotten you, {first_name}", "Our busy season means a longer list, but your repair is on it and moving forward every week."),
    ("Your weekly repair update", "Every Thursday brings you a little closer to getting your repair done."),
    ("Thanks for your patience, {first_name}", "We know you've been waiting, and we appreciate you hanging in there with us. Your repair is still moving up the list."),
]

REPAIR_ROOF_TIPS = [
    "After a heavy rain, take a quick look at your ceilings and the tops of your walls. A new water spot is worth a call, even before your repair.",
    "Keep your gutters and downspouts clear. Water that backs up can find its way under shingles and make a small problem bigger.",
    "Trim tree branches that hang over the roof. They scrape shingles in the wind and drop leaves that hold moisture.",
    "Peek into your attic with a flashlight on a sunny day. Daylight coming through or damp insulation is good to know about before your repair.",
    "Look for shingle granules collecting at the bottom of your downspouts. A lot of them can be a sign of worn shingles, and we're happy to check.",
    "Please stay off the roof. If something looks wrong after a storm, snap a photo from the ground and call us at (317) 886-7436.",
    "Good attic airflow helps shingles last and keeps ice from building up along the edges in winter. Make sure your soffit vents aren't blocked by insulation or storage.",
]

REPAIR_SIDING_TIPS = [
    "Rinse your siding once a year with a garden hose to keep it looking new; skip the pressure washer.",
    "Keep sprinklers aimed away from your walls so water doesn't sit behind the siding.",
    "Keep mulch and soil a few inches below the bottom row of siding.",
    "Trim shrubs so they don't rub against the house.",
    "Check the caulk around your windows and doors. Gaps let water and drafts in, and they're easy to spot from the ground.",
    "After a storm, walk around the house and look for loose, cracked, or missing pieces. A quick photo helps us when we get there.",
]

# ---------------------------------------------------------------------------
# SHARED EMAILS
# ---------------------------------------------------------------------------
W6_SUBJECT = "The protection that comes with your new {project_word}"
W6_BODY = """
{position_block}

Here's something to look forward to. {warranty_sentence}

If you ever have a question about it down the road, you don't need to track down the manufacturer or dig through paperwork. Just call us and we'll take it from there.

That's one less thing on your plate, so you can just enjoy your new {project_word}.

The Indy Roof and Restoration Team
"""
W6_WARRANTY_WITH_MFR = (
    "Your new {project_word} is backed by a manufacturer warranty from {manufacturer}, and we hold "
    "that warranty for you. There's nothing for you to register, file, or keep track of."
)
# Manufacturer unknown on the job: same sentence without the brand
W6_WARRANTY_NO_MFR = (
    "Your new {project_word} is backed by a manufacturer warranty, and we hold that warranty for "
    "you. There's nothing for you to register, file, or keep track of."
)
W6_WARRANTY_GUTTERS = "Your new gutters are backed by our workmanship, and we stand behind every install."

W7_SUBJECT = "Know someone who needs a new roof? Here's $200."
W7_BODY = """
{position_block}

Our favorite way to grow is through people like you. If a friend, family member, neighbor, or coworker has been thinking about their roof, we'd love to take care of them too.

**Here's how our referral program works:** for every person you refer who gets a new roof with us, we'll send you **$200**. There's no limit, so the more people you help, the more you earn.

Referring someone is easy:

{referral_steps}

Everyone you send our way gets a free inspection with no pressure, and the same care you've gotten from us.

Thanks for spreading the word,

The Indy Roof and Restoration Team
"""
W7_STEPS_WITH_REP = """1. **Send their name and number to {rep_name}**, your field inspector, at {rep_phone}. We'll reach out and take it from there.
2. **Or pass {rep_name}'s contact info along** to your friend and have them mention your name when they call."""
# Rep contact info missing on the job: point to the office instead
W7_STEPS_NO_REP = """1. **Send their name and number to our office** at (317) 886-7436. We'll reach out and take it from there.
2. **Or pass our number along** to your friend and have them mention your name when they call."""

W8_SUBJECT = "A personal note from Aaron"
W8_BODY = """
{position_block}

I wanted to reach out personally and say thank you. You've been in our build queue for about two months now, and I know waiting on a project like this isn't anyone's favorite thing.

I started Indy Roof and Restoration in 2018 with a simple idea: do every job the way I'd want it done on my own family's home. Sometimes that means a longer wait during our busy season. But it also means when it's your turn, you'll get a crew that takes its time and does it right.

You haven't been forgotten, and you won't be. If there's ever anything we can do for you while you wait, call us at (317) 886-7436.

Thank you for trusting us with your home.

Aaron

Owner, Indy Roof and Restoration
"""

ROTATION_BODY = """
{position_block}

{opener}

**This week's tip:** {tip}

The Indy Roof and Restoration Team
"""
ROTATION = [
    ("Still holding your spot, {first_name}", "Just checking in to let you know your build is right where it should be in our schedule."),
    ("Your weekly {project_word} update", "Another week of builds in the books, and you're closer than ever."),
    ("Thanks for your patience, {first_name}", "We know you've been waiting a while, and we appreciate you hanging in there with us."),
    ("We haven't forgotten you", "Our busy season means a longer line, but your spot is locked in and moving forward."),
    ("Your new {project_word} is getting closer", "Every Thursday brings you a little closer to build day."),
]

# ---------------------------------------------------------------------------
# TRIGGERED EMAILS
# ---------------------------------------------------------------------------
GETTING_CLOSE_SUBJECT = "You're almost at the front of the line!"
GETTING_CLOSE_BODY = """
This is the email we've been looking forward to sending. **You're nearly at the front of our build schedule.** Depending on weather, your build could be coming up very soon.

Our scheduling team will reach out to set your date. Here's your final checklist so you're ready to go:

{checklist}

{almost_here} We can't wait to show you the finished result.

The Indy Roof and Restoration Team
"""
GETTING_CLOSE_CHECKLIST_ROOF = """- Plan to park on the street on build day so the driveway is clear
- Take pictures and mirrors off exterior walls
- Cover items stored in the attic with a sheet or drop cloth
- Make a plan for pets during the noisy part of the day
- Let us know about sprinklers, gardens, or anything delicate near the house
- Unlock any gates so the crew can reach every side of the home"""
GETTING_CLOSE_CHECKLIST_SIDING = """- Furniture and decor 10 feet from the walls
- Wall hangings down on exterior walls
- Cameras, house numbers, and fixtures removed or flagged
- Gates unlocked
- Pets and parking planned"""
GETTING_CLOSE_CHECKLIST_GUTTERS = """- Ground under eaves cleared
- Driveway space for the gutter truck
- Sprinkler and drain lines flagged
- Gates unlocked"""
ALMOST_HERE_ROOF_COLOR = "Your {shingle_color} roof is almost here."
ALMOST_HERE_ROOF = "Your new roof is almost here."
ALMOST_HERE_SIDING = "Your new siding is almost here."
ALMOST_HERE_GUTTERS = "Your new gutters are almost here."

WEATHER_SUBJECT = "A quick weather update from our crews"
WEATHER_BODY = """
If you looked outside this week, you already know. Mother Nature kept our crews off the roofs for several days, so the schedule moved a little slower than usual.

Here's what that means for you: **your spot hasn't changed.** As soon as the weather clears, our crews get right back to work, and good weeks after a rainy stretch tend to move quickly.

We'll never put a roof on in conditions that could compromise it. Your home deserves better than that.

Thanks for sticking with us,

The Indy Roof and Restoration Team
"""

# ---------------------------------------------------------------------------
# RESCHEDULES
# ---------------------------------------------------------------------------
RESCHEDULE_SUBJECT = "A quick update on your build date"
RESCHEDULE_BODY = """
Your build that was set for {original_date} had to be rescheduled. We're already working to get you a new date as soon as possible.

We know you were looking forward to it, and so were we. Here's what matters most: **you are not going back to the end of the line.** Your project stays at the front of our schedule, and our team will reach out as soon as your new date is set, if we haven't already. If you've already heard from us with your new date, you're all set.

Nothing changes on your end. Your materials, colors, and project plan all stay exactly the same.

Thank you for your patience,

The Indy Roof and Restoration Team
"""

FRONT_OF_LINE_SUBJECT = "You're still at the front of the line, {first_name}"
FRONT_OF_LINE_BODY = """
Just a quick note to let you know your project is still at the top of our schedule while we lock in your new build date. As soon as it's set, you'll hear from us right away. If our team has already reached out with your new date, you can disregard this note.

**This week's tip:** {tip}

The Indy Roof and Restoration Team
"""

SECOND_RESCHEDULE_SUBJECT = "We're sorry to move your build again"
SECOND_RESCHEDULE_BODY = """
Your build date had to be rescheduled again, and we know that's frustrating.

You're still at the very front of our schedule, and we're working to get you a new date as soon as possible.

We appreciate you sticking with us, and we're going to make it worth the wait.

The Indy Roof and Restoration Team
"""

INTERNAL_SECOND_RESCHEDULE_SUBJECT = "Second reschedule: {customer_name}, {job_address}"
INTERNAL_SECOND_RESCHEDULE_BODY = """
{pm_name} and {rep_name},

The build for {customer_name} at {job_address} has now been rescheduled twice. The customer has been sent an automated apology email.

If you haven't already, please reach out to them personally today to check in and talk through next steps. A call from someone they know goes a long way at this point.

Customer phone: {customer_phone}

JobNimbus: {job_link}
"""

# ---------------------------------------------------------------------------
# YOU'RE SCHEDULED (fun one). Goes out about an hour after JobNimbus's official
# "Project Update" email, once per job. Dates are fine here: the job is scheduled.
# DRAFT: written by Claude from Aaron's direction ("fun and exciting, not technical").
# ---------------------------------------------------------------------------
SCHEDULED_SUBJECT = "It's official, {first_name}! You're on the calendar \U0001F389"
SCHEDULED_BODY = """
{official_email_line}

{date_line} Unless Mother Nature decides to crash the party with some pesky weather (boo, hiss). If she does, we'll get you right back on the calendar.

You waited patiently, you stuck with us, and now it's almost go time. Our whole team is fired up for you. Consider this your official high five. \u270B

{finish_line}

Let's do this,

The Indy Roof and Restoration Team
"""
SCHEDULED_OFFICIAL_LINE = (
    "You probably just got a more official email from us with all the details. Give that one a "
    "read when you get a chance. This one's just for fun."
)
SCHEDULED_DATE_LINE = "**Your {project_word} is scheduled for {scheduled_date}!**"
SCHEDULED_NO_DATE_LINE = "**Your {project_word} is officially on the calendar!**"
SCHEDULED_FINISH_INSTALL = (
    "Very soon you'll pull into your driveway and see your home with a brand new {project_word}. "
    "Our customers tell us that moment never gets old, and we can't wait to be part of it for you."
)
SCHEDULED_FINISH_REPAIR = (
    "Very soon this will be one less thing on your list, and you can get back to enjoying your home."
)

OFFICE_FLAG_SUBJECT = "Build queue email flag: {customer_name}"
OFFICE_FLAG_BODY = """
{flag_text}

Customer: {customer_name}

Address: {job_address}

JobNimbus: {job_link}
"""
