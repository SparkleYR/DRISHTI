package com.drishti.app

import com.drishti.app.walk.parseLocateTarget
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Routing for the combined "Ask" gesture: does a spoken phrase become an
 * "Ask -> Lock" target (and what target), or fall through to Scene Mode?
 */
class LocateRoutingTest {

    private val markers = listOf(
        "find ", "locate ", "look for ", "search for ", "point me to ",
        "where is ", "where's ", "wheres ", "take me to ", "guide me to ", "go to ",
    )

    private fun route(phrase: String?) = parseLocateTarget(phrase, markers)

    @Test
    fun `keyword mid-sentence with politeness and trailing clause`() {
        assertEquals("blue bucket", route("can you locate me the blue bucket which I had"))
    }

    @Test
    fun `plain imperative`() {
        assertEquals("exit", route("find the exit"))
        assertEquals("registration desk", route("where is the registration desk"))
        assertEquals("chair", route("look for a chair"))
        assertEquals("water cooler", route("take me to the water cooler"))
    }

    @Test
    fun `scene questions do not route to locate`() {
        assertNull(route("what is in front of me"))
        assertNull(route("describe the room"))
        assertNull(route("is the path clear"))
        assertNull(route("find out what is ahead"))
        assertNull(route(""))
        assertNull(route(null))
    }

    @Test
    fun `bare keyword with no target falls through`() {
        assertNull(route("locate"))
        assertNull(route("where is it"))
    }

    @Test
    fun `does not match inside another word`() {
        assertNull(route("relocated furniture everywhere"))
    }

    @Test
    fun `verb-final phrasing uses text before the keyword`() {
        // Hindi: "नीली बाल्टी ढूंढो" == "blue bucket, find"
        assertEquals("नीली बाल्टी", parseLocateTarget("नीली बाल्टी ढूंढो", listOf("ढूंढो ", "खोजो ")))
    }

    @Test
    fun `conversational trailing clauses stripped`() {
        assertEquals("towel", route("locate the towel I previously had"))
        assertEquals("towel", route("find the towel I saw earlier"))
        assertEquals("bag", route("where is the bag I left just now"))
    }

    @Test
    fun `trailing punctuation and filler stripped`() {
        assertEquals("main door", route("please find the main door."))
        assertEquals("stairs", route("guide me to the stairs that I passed"))
    }
}
