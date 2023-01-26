% PURPOSE: An example using driftmap,
%          to examine the distribution of
%          a vector-variable over a map
%---------------------------------------------------
% USAGE: driftmap_d
%---------------------------------------------------


load countyg.data;


y1 = countyg(:,4); % county employment growth rate
y80 = countyg(:,8); % 1980 log employment
educ = countyg(:,17); % share of local government spending on education 1982

latt = countyg(:,2);
long = countyg(:,3);

tt=0:30:360;
nrot = length(tt);
for i=1:nrot;
rot = tt(i);
driftmap(-latt,-long,y80,10,10,1,rot); % using points
pause;
end;


% columns
%   1     STATE/county = state FIPS code
%   2     latitude centroid for the county
%   3     longitude centroid for the county
%   4     EMPGR = employment growth rate (1980-90)
%   5     POPGR = population growth rate (1980-90)
%   6     DEMPGR = employment growth rate minus
%                 mean across all counties in same state (1980-90)
%   7     DPOPGR = population growth rate minus
%                 mean across all counties in same state (1980-90)
%   8     LOGEMP = natural logarithm of employment 1980
%   9     LOGPOP = natural logarithm of population 1980
%   10    EDENS = employment density (employment per square mile) 1980
%   11    PDENS = population density (population per square mile) 1980
%   12    LOGAREA = natural logarithm of land area 1980
%   13    COLLRATE = fraction of adult population with bachelor's degree
%                or more 1980
%   14    MFGRATE = fraction of employment in manufacturing 1980
%   15    UR = unemployment rate 1980
%   16    PCINC = per capita income (dollars) 1979
%   17    EDUCSH = share of local government spending on education 1982
%   18    HWSH = share of local government spending on highways 1982
%   19    POLSH = share of local government spending on police 1982
%   20    NWRATE = fraction of population that is not white 1980
%   21    URBAN = urban indicator variable
%                (= 1 if county located in metropolitan area) 1990
%   22    RURAL = rural indicator variable
%                ( = 1 if county located outside metropolitan area) 1990
%
