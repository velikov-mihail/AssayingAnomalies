% PURPOSE: An example using boxplotmap
%          to examine the boxplot of
%          a vector-variables over a map
%---------------------------------------------------
% USAGE: boxplotmap_d
%---------------------------------------------------


clear all;

load ohioschool.data;
long = ohioschool(:,2);
latt = ohioschool(:,3);
scores = ohioschool(:,22);  % median 4th grade proficiency score
salary = ohioschool(:,9); % avg teacher salary

boxplotmap(long,latt,salary); % using colored dots

% boxplotmap(long,latt,salary,[],[],1); % using labels

% variables are:
% data for 2001-02 year
% col 1 = zip code
% col 2 = longitude  (zip centroid)
% col 3 = lattitude (zip centroid)
% col 4 = buidling irn
% col 5 = district irn
% col 6 = # of teachers (FTE 2001-02)
% col 7 = teacher attendance rate
% col 8 = avg years of teaching experience
% col 9 = avg teacher salary
% col 10 = Per Pupil Spending on Instruction
% col 11 = Per Pupil Spending on Building Operations
% col 12 = Per Pupil Spending on Administration
% col 13 = Per Pupil Spending on Pupil Support
% col 14 = Per Pupil Spending on Staff Support
% col 15 = Total Expenditures Per Pupil
% col 16 = Per Pupil Spending on Instruction % of Total Spending Per Pupil
% col 17 = Per Pupil Spending on Building Operations % of Total Spending Per Pupil
% col 18 = Per Pupil Spending on Administration % of Total Spending Per Pupil
% col 19 = Per Pupil Spending on Pupil Support % of Total Spending Per Pupil
% col 20 = Per Pupil Spending on Staff Support % of Total Spending Per Pupil
% col 21 = irn number
% col 22 = avg of all 4th grade proficiency scores
% col 23 = median of 4th grade prof scores
% col 24 = building enrollment
% col 25 = short-term students < 6 months
% col 26 = 4th Grade (or 9th grade) Citizenship % Passed 2001-2002
% col 27 = 4th Grade (or 9th grade)  math % Passed 2001-2002
% col 28 = 4th Grade (or 9th grade)  reading % Passed 2001-2002
% col 29 = 4th Grade (or 9th grade)  writing % Passed 2001-2002
% col 30 = 4th Grade (or 9th grade)  science % Passed 2001-2002
% col 31 = pincome per capita income in the zip code area
% col 32 = nonwhite percent of population that is non-white
% col 33 = poverty percent of population in poverty
% col 34 = samehouse % percent of population living in same house 5 years ago
% col 35 = public % of population attending public schools
% col 36 = highschool
% col 37 = assoc educ attainment for 25 years plus
% col 38 = college
% col 39 = grad
% col 40 = prof


