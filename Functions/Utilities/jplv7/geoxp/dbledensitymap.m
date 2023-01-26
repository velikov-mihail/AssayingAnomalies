function [out]=dbledensitymap(long,lat,var1,var2,a1,a2,varargin)
% PURPOSE: This function links a map and two density estimators
%------------------------------------------------------------------------
% USAGE: out=dbledensitymap(long,lat,var1,var2,alpha1,alpha2,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           var1 = n x 1 vector of the first variable to study
%           var2 = n x 1 vector of the second variable to study
%           alpha1 = used to calculate the bandwidth of the first density. band1=(alpha1/100)*(max(var1)-min(var1))/2
%           alpha2 = used to calcule the bandwidth of the second density. band2=(alpha2/100)*(max(var2)-min(var2))/2
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% NOTES: This function uses the function kern_den to calculate the densities
%------------------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         Select intervals on a density graph by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                            - left click to set the other points
%                                                            - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses kern_den.m, setdens3.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
vectx=[];
vecty=[];
inter=[];
iner2=[];
name1=inputname(3);
name2=inputname(4);
global v1glob;
v1glob=var1;
global v2glob;
v2glob=var2;
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save dbldensfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;  
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);

if c==1
     plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%

warning off;
global h1;
global h2;
warning on;
global Hslide1;
global Ht1;
global Hslide2;
global Ht2;
global newx;
global dens;
global newx2;
global dens2;
% Trace the density estimators
Axis2=subplot(2,2,2);
newx=linspace(min(var1),max(var1)+0.5,100);
h1=(a1/100)*(max(var1)-min(var1))/2;
dens=kern_den(var1,h1,newx);
plot(newx,dens,'b-');
title(name1);
axis manual;

Axis3=subplot(2,2,4);
newx2=linspace(min(var2),max(var2)+0.5,100);
h2=(a2/100)*(max(var2)-min(var2))/2;
dens2=kern_den(var2,h2,newx2);
plot(newx2,dens2,'b-');
title(name2);
axis manual;
subplot(Axis1);
axis manual;
%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Create the sliders

Hslide1=uicontrol('Style','slider','Min',0,'Max',100,'Value',a1);
Ht1=uicontrol('Style','text','String',['a1=' num2str(get(Hslide1,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
Hslide2=uicontrol('Style','slider','Min',0,'Max',100,'Value',a2,'Position',[300,20,60,20]);
Ht2=uicontrol('Style','text','String',['a2=' num2str(get(Hslide2,'Value')),'%'],'Position',[380,20,60,20],'Enable','inactive');
set(Hslide1,'Callback','setdens3'); % Call to setdens3.m when one of the sliders is clicked
set(Hslide2,'Callback','setdens3');
%%%%%%%%%%%%%%%%%%%%

 % Main loop
 intersav=[];
 intersav2=[];
 intersav3=[];
 intersav4=[];
 maptest=0;
 densitytest1=0;
 densitytest2=0;
 BUTTON=0;
 while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
     Posfig=get(1,'Position');
     PosAx1=get(Axis1,'Position');
     PosAx2=get(Axis2,'Position');
     PosAx3=get(Axis3,'Position');
     %redraw the graphs
     % Axe2
     subplot(Axis2);
     hold on;
     cla;
     Iselect=find(obs==1);
     Iunselect=find(obs==0);
     plot(newx,dens,'b-');
     if ~isempty(Iselect)
         if maptest==1
            denspart1=kern_den(var1(Iselect),h1,newx);
            if max(denspart1)>max(dens)
                hold off;
                plot(newx,denspart1,'r-');
                title(name1);
                hold on;
                plot(newx,dens,'b-');
            else
                plot(newx,denspart1,'r-');
            end;
         elseif densitytest1==1
             if ~isempty(intersav) & (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
                 intersav2=sort([intersav2,intersav]);
             end;
             if ~isempty(intersav2)    
                 for i=1:2:length(intersav2)
                     m=intersav2(i);                   
                     M=intersav2(i+1);
                     if i==1
                         ind=find((newx>=m) & (newx<=M));
                         if ~isempty(ind)
                             fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'m');
                         end;
                     else
                         ind=find((newx>=m) & (newx<=M));
                         if ~isempty(ind)
                             fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'m');
                             ind=find(newx>=intersav2(i-1)-(newx(2)-newx(1)) & newx<=m+(newx(2)-newx(1)));
                             fill([min(newx(ind)) newx(ind) max(newx(ind))],[0 dens(ind) 0],'w');
                         end;
                     end;
                         
                 end;
             end;
         elseif densitytest2==1
            denspart1=kern_den(var1(Iselect),h1,newx);
            if max(denspart1)>max(dens)
                hold off;
                plot(newx,denspart1,'g-');
                title(name1);
                hold on;
                plot(newx,dens,'b-');
            else
                plot(newx,denspart1,'g-');
            end;
         end;
     end;
     hold off;
     %%%%%%%%%%%%%%%
     %%%% Axe 3
     subplot(Axis3);
     hold on;
     cla;
     Iselect=find(obs==1);
     Iunselect=find(obs==0);
     plot(newx2,dens2,'b-');
     if ~isempty(Iselect)
         
         if maptest==1
             denspart2=kern_den(var2(Iselect),h2,newx2);
             if max(denspart2)>max(dens2)
                hold off;
                plot(newx2,denspart2,'r-');
                title(name2);
                hold on;
                plot(newx2,dens2,'b-');
            else
                plot(newx2,denspart2,'r-');
            end;
         elseif densitytest1==1
             denspart2=kern_den(var2(Iselect),h2,newx2);
             if max(denspart2)>max(dens2)
                hold off;
                plot(newx2,denspart2,'m-');
                title(name2);
                hold on;
                plot(newx2,dens2,'b-');
            else
                plot(newx2,denspart2,'m-');
            end;
         elseif densitytest2==1
             if ~isempty(intersav3) & (currentpoint(1)>=PosAx3(1)*Posfig(3)) & (currentpoint(1)<=(PosAx3(1)+PosAx3(3))*Posfig(3)) & (currentpoint(2)>=PosAx3(2)*Posfig(4)) & (currentpoint(2)<=(PosAx3(2)+PosAx3(4))*Posfig(4))
                 intersav4=sort([intersav4,intersav3]);
             end;
             if ~isempty(intersav4)    
                 for i=1:2:length(intersav4)
                     m=intersav4(i);                   
                     M=intersav4(i+1);
                     if i==1
                         ind=find((newx2>=m) & (newx2<=M));
                         if ~isempty(ind)
                             fill([min(newx2(ind)) newx2(ind) max(newx2(ind))],[0 dens2(ind) 0],'g');
                         end;
                     else
                         ind=find((newx2>=m) & (newx2<=M));
                         if ~isempty(ind)
                             fill([min(newx2(ind)) newx2(ind) max(newx2(ind))],[0 dens2(ind) 0],'g');
                             ind=find(newx2>=intersav4(i-1)-(newx2(2)-newx2(1)) & newx2<=m+(newx2(2)-newx2(1)));
                             fill([min(newx2(ind)) newx2(ind) max(newx2(ind))],[0 dens2(ind) 0],'w');
                         end;
                     end;                
                 end;
             end;
         end;
     end;
     hold off;
     %%%%%%%%%%%%%%
     % Axe 1
    subplot(Axis1);
    hold on;
    cla;
    if c==1
            plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif densitytest1==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'mo');  
            else
                plot(long(Iselect),lat(Iselect),'m.');      
            end;
        elseif densitytest2==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'gd');  
            else
                plot(long(Iselect),lat(Iselect),'g.');      
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%
     %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
     
     [x,y,BUTTON]=ginput(1);
     currentpoint=get(1,'CurrentPoint');
     % map selection
     if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
         if maptest==0      
             maptest=1;
             densitytest1=0;
             densitytest2=0;
             obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
         %%%%%%%%%%%%%%%%%%%
     %%%%%%%%%%%%%%%%%%%%%%%
     % density selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
         if densitytest1==0
             densitytest1=1;
             densitytest2=0;
             intersav2=[];
             maptest=0;
             obs=zeros(size(long,1),1);
             if  BUTTON~=3 & BUTTON~=2 
                 inter=x;
                 intersav=[];
             end;
             p=0;
         end;
         [obs,inter,intersav,p]=selectstat('density',obs,var1,inter,intersav,p,x,BUTTON);
         %%%%%%%%%%%%%%%%%%%%
    elseif (currentpoint(1)>=PosAx3(1)*Posfig(3)) & (currentpoint(1)<=(PosAx3(1)+PosAx3(3))*Posfig(3)) & (currentpoint(2)>=PosAx3(2)*Posfig(4)) & (currentpoint(2)<=(PosAx3(2)+PosAx3(4))*Posfig(4))
         if densitytest2==0
             densitytest1=0;
             densitytest2=1;
             intersav4=[];
             maptest=0;
             obs=zeros(size(long,1),1);
             if  BUTTON~=3 & BUTTON~=2 
                 inter2=x;
                 intersav3=[];
             end;
             p5=0;
         end;
         [obs,inter2,intersav3,p5]=selectstat('density',obs,var2,inter2,intersav3,p5,x,BUTTON);
    end;
     %%%%%%%%%%%%%%%%%%%%%%
 end;
 out=obs;
 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%